"""HTTP API around the CineGraph Responser, used by the web interface.

Run locally:
    uvicorn server.api:app --port 8000

The graph, embeddings and image map are loaded once at startup (or by
``warm()`` when the module is imported by the Modal app before a memory
snapshot). Answers are serialized behind a lock because the Responser keeps
per-request state and its trace is captured from stdout.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import sys
import threading
import time
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional

import rdflib
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from core.data import (
    WD,
    WDT,
    build_label_maps,
    load_embeddings,
    load_graph,
    load_image_map,
    load_ratings,
)
from core.linker import get_linker
from core.recommender import LAST_RUN as REC_LAST_RUN, recommend_movies
from core.responser import Responser
from server.catalog import Catalog

TMDB_BASE = "https://image.tmdb.org/t/p"
MAX_MESSAGE_CHARS = 300
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "20"))
MAX_CARDS = 8

P31 = rdflib.URIRef(str(WDT) + "P31")
P57 = rdflib.URIRef(str(WDT) + "P57")
P136 = rdflib.URIRef(str(WDT) + "P136")
P345 = rdflib.URIRef(str(WDT) + "P345")
P577 = rdflib.URIRef(str(WDT) + "P577")
FILM = rdflib.URIRef(str(WD) + "Q11424")
HUMAN = rdflib.URIRef(str(WD) + "Q5")

# Answers that report a failure rather than a result
_MISS_PREFIXES = (
    "could not",
    "not a recommendation",
    "embeddings data not loaded",
    "entity '",
    "relation not in",
    "predicted entity not found",
)


class _State:
    graph: Optional[rdflib.Graph] = None
    responser: Optional[Responser] = None
    ent_to_lbl: Dict[Any, str] = {}
    lbl_to_ent: Dict[str, Any] = {}
    images: Dict[str, Dict[str, Any]] = {}
    ratings: Dict[str, float] = {}
    catalog: Optional[Catalog] = None
    embeddings: bool = False
    load_seconds: float = 0.0
    triples: int = 0


STATE = _State()
_warm_lock = threading.Lock()
_answer_lock = threading.Lock()


def warm() -> None:
    """Load every dataset once. Safe to call more than once."""
    with _warm_lock:
        if STATE.responser is not None:
            return
        t0 = time.time()
        graph = load_graph()
        try:
            ent, rel, ent_ids, rel_ids, id_to_ent = load_embeddings()
            responser = Responser(ent, rel, ent_ids, rel_ids, id_to_ent)
            STATE.embeddings = True
        except Exception as exc:  # embeddings are optional
            print(f"[api] embeddings unavailable: {exc}")
            responser = Responser()
        ent_to_lbl, lbl_to_ent, _ = build_label_maps(graph)
        STATE.images = load_image_map()
        STATE.ratings = load_ratings()
        STATE.graph = graph
        STATE.ent_to_lbl = ent_to_lbl
        STATE.lbl_to_ent = lbl_to_ent
        STATE.triples = len(graph)
        STATE.catalog = Catalog(graph, ent_to_lbl, STATE.ratings)
        get_linker(graph, ent_to_lbl)  # build the label index before the memory snapshot
        STATE.load_seconds = round(time.time() - t0, 1)
        STATE.responser = responser
        print(f"[api] ready: {STATE.triples} triples in {STATE.load_seconds}s")


# ---------- enrichment ----------

def _qid(uri: str) -> Optional[str]:
    s = str(uri)
    return s[len(str(WD)):] if s.startswith(str(WD)) else None


def _label(uri: Any) -> Optional[str]:
    ref = uri if isinstance(uri, rdflib.URIRef) else rdflib.URIRef(str(uri))
    return STATE.ent_to_lbl.get(ref)


def tmdb_url(path: str, kind: str) -> str:
    """Map an images.json path ('0344/<hash>.jpg' or '0344/<hash>') to the TMDB CDN."""
    name = path.rsplit("/", 1)[-1]
    if "." not in name:
        name += ".jpg"
    size = "w1280" if kind.startswith("backdrop") else "w500"
    return f"{TMDB_BASE}/{size}/{name}"


def entity_card(uri: str) -> Optional[Dict[str, Any]]:
    """Small display card for a film or person in the graph."""
    g = STATE.graph
    if g is None:
        return None
    ref = rdflib.URIRef(uri)
    label = _label(ref)
    if not label:
        return None
    imdb = g.value(ref, P345)
    imdb = str(imdb) if imdb else None
    is_film = (ref, P31, FILM) in g
    is_person = (ref, P31, HUMAN) in g
    card: Dict[str, Any] = {"qid": _qid(uri), "label": label, "imdb": imdb, "image": None}
    if is_film:
        card["type"] = "film"
        date = g.value(ref, P577)
        card["year"] = str(date)[:4] if date else None
        card["directors"] = [l for l in (_label(d) for d in g.objects(ref, P57)) if l][:2]
        card["genres"] = [l for l in (_label(x) for x in g.objects(ref, P136)) if l][:3]
        rating = STATE.ratings.get(uri)
        card["rating"] = round(rating, 2) if rating else None
        if imdb and imdb in STATE.images.get("poster", {}):
            card["image"] = tmdb_url(STATE.images["poster"][imdb], "poster")
        if imdb and imdb in STATE.images.get("backdrop", {}):
            card["backdrop"] = tmdb_url(STATE.images["backdrop"][imdb], "backdrop")
    elif is_person:
        card["type"] = "person"
        if imdb and imdb in STATE.images.get("profile", {}):
            card["image"] = tmdb_url(STATE.images["profile"][imdb], "profile")
    else:
        card["type"] = "other"
    return card


def _cards(uris: List[str]) -> List[Dict[str, Any]]:
    out, seen = [], set()
    for u in uris:
        if u in seen:
            continue
        seen.add(u)
        c = entity_card(u)
        if c:
            out.append(c)
        if len(out) >= MAX_CARDS:
            break
    return out


def _trace(raw: str) -> List[str]:
    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("["):
            continue
        if line.startswith("[data]") or line.startswith("[graph]"):
            continue
        lines.append(line[:240])
    return lines[:40]


def build_reply(message: str, answer: str, meta: Dict[str, Any], trace_raw: str, ms: float) -> Dict[str, Any]:
    route = meta.get("route") or "factual"
    text = (answer or "").strip()
    image = None
    if text.startswith("image:"):
        info = meta.get("image") or {}
        kind = info.get("kind") or "profile"
        image = {
            "url": tmdb_url(text[len("image:"):], kind),
            "kind": {"backdrop_cast": "scene", "backdrop": "scene"}.get(kind, kind),
            "label": info.get("entity_label"),
        }
        text = ""
    ok = bool(image) or not text.lower().startswith(_MISS_PREFIXES)
    note = None
    if route == "prediction":
        m = re.search(r"\s*\(Note: (.*)\)\s*$", text)
        if m:
            note = m.group(1).strip()
            text = text[: m.start()]
        text = re.sub(r"\s*\(type: Q\d+\)", "", text).strip()
    if route == "multimedia" and not image:
        ok = False

    subject = None
    if meta.get("entity_uri"):
        subject = entity_card(meta["entity_uri"]) or {"label": _label(meta["entity_uri"]), "qid": _qid(meta["entity_uri"])}

    if route == "recommendation":
        uris = [u for u in (meta.get("recommendation_uris") or []) if u] or [
            str(STATE.lbl_to_ent[t]) for t in meta.get("recommendations", []) if t in STATE.lbl_to_ent]
        seeds = list(meta.get("seed_uris") or []) or [
            str(STATE.lbl_to_ent[t]) for t in meta.get("seeds", []) if t in STATE.lbl_to_ent]
        cards = _cards(uris)
        seed_cards = _cards(seeds)
    elif route == "multimedia":
        info = meta.get("image") or {}
        cards = _cards([u for u in (info.get("entity_uri"), info.get("movie_uri")) if u])
        seed_cards = []
    else:
        cards = _cards(meta.get("answer_uris", []))
        seed_cards = []

    objects = [l for l in (_label(u) for u in meta.get("answer_uris", [])) if l][:12]
    if not meta.get("via_films") and not meta.get("compact"):  # these answers are already short
        text = _summarize_list(text, route, len(set(meta.get("answer_uris", []))), len(meta.get("parts") or []),
                               bool(meta.get("inverse")))

    # A prediction whose nearest entity has no label in the graph is only a bare Q-ID: not an answer.
    if route == "prediction" and ok and not objects and re.search(r"\bQ\d{2,}\b", text):
        ok = False
        text = "No answer. The embedding prediction landed on an entity with no name in the graph."

    # Non-film subjects (character, series) are answered through their films by the agent; show those films.
    hint = None
    suggestions: List[Dict[str, Any]] = []
    suggestions_title = "Films with a similar title in the graph"
    via = [u for u in (meta.get("via_films") or []) if u]
    if via and STATE.catalog is not None:
        by_qid = STATE.catalog.film_by_qid
        rows = [by_qid[q] for q in (_qid(u) for u in via) if q in by_qid]
        suggestions = [STATE.catalog._public(r) for r in rows[:12]]
        label = (subject or {}).get("label") or (meta.get("intent") or {}).get("mention")
        if label:
            suggestions_title = f"Films linked to {label}"
            hint = f"“{label}” is not a film in the graph; the answer is read from the films linked to it."
    elif subject and subject.get("type") not in ("film", None) and route in ("factual", "prediction"):
        kind = "a person" if subject.get("type") == "person" else "not a film"
        if not meta.get("inverse"):
            hint = f"“{subject.get('label')}” matched {subject.get('qid')}, which is {kind} in the graph."
    if not suggestions and (hint or not ok) and STATE.catalog is not None and route != "multimedia":
        probe = subject.get("label") if subject else _title_guess(message)
        if probe:
            suggestions = STATE.catalog.list_films(probe, "popular", 0, 8)["films"]

    return {
        "message": message,
        "answer": text,
        "ok": ok,
        "note": note,
        "hint": hint,
        "suggestions": suggestions,
        "suggestions_title": suggestions_title,
        "alternatives": _alternatives(message, meta),
        "reading": _reading(meta, subject, len(via)),
        "route": route,
        "image": image,
        "subject": subject,
        "relation": meta.get("relation"),
        "property": (meta.get("property_uri") or "").rsplit("/", 1)[-1] or None,
        "inverse": bool(meta.get("inverse")),
        "objects": objects,
        "count": len(set(meta.get("answer_uris", []))),
        "cards": cards,
        "seeds": seed_cards,
        "rewritten": meta.get("rewritten"),
        "sparql": _tidy_sparql(meta.get("sparql")),
        "trace": _trace(trace_raw),
        "latency_ms": round(ms),
    }


def _alternatives(message: str, meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Other entities with the same name; `ask` repeats the question with the title made specific."""
    out = []
    mention = ((meta.get("intent") or {}).get("mention") or "").strip()
    for alt in (meta.get("alternatives") or [])[:5]:
        label = alt.get("label")
        if not label or not alt.get("qid"):
            continue
        year = alt.get("year")
        full = f"{label} ({year})" if year else label
        target = mention if mention and mention.lower() in message.lower() else label
        pat = re.compile(re.escape(target), re.I)
        ask = pat.sub(lambda _m: full, message, count=1) if pat.search(message) else f"{message.rstrip(' ?.')} ({full})?"
        out.append({"qid": alt["qid"], "label": label, "year": year, "kind": alt.get("kind"), "ask": ask})
    return out


def _reading(meta: Dict[str, Any], subject: Optional[Dict[str, Any]], via_count: int) -> Optional[Dict[str, Any]]:
    """How the question was read: relation, subject, subject kind, films used, further parts."""
    intent = meta.get("intent")
    if not intent:
        return None
    parts = []
    for p in meta.get("parts") or []:
        parts.append({"relation": p.get("relation"), "answer": p.get("answer")})
    return {
        "relation": meta.get("relation") or intent.get("relation"),
        "subject": (subject or {}).get("label") or intent.get("mention"),
        "subject_kind": meta.get("subject_kind"),
        "via_count": via_count,
        "parts": parts,
    }


def _title_guess(message: str) -> Optional[str]:
    """The words after 'of'/'directed'/etc., good enough to look up similarly named films."""
    m = re.search(r"(?:of|directed|direct|wrote|for|about)\s+(?:the\s+movie\s+|the\s+film\s+)?[\"'“]?([^?\"”]+)", message, re.I)
    guess = (m.group(1) if m else "").strip(" .'")
    return guess if 2 <= len(guess) <= 60 else None


_LIST_HEAD = re.compile(r"^(.+?)\s+(?:include|includes|are|were)\s+\S")


def _summarize_list(text: str, route: str, n: int, n_parts: int = 1, inverse: bool = False) -> str:
    """Long 'A and B and C ...' answers repeat the cards; keep the sentence head and the count.

    Answers to several sub-questions stay whole: collapsing them would drop every other part.
    """
    if route != "factual" or n <= 3 or n_parts > 1:
        return text
    noun = "titles" if inverse else "entries"
    m = _LIST_HEAD.match(text)
    if m:
        return f"{m.group(1)}: {n} {noun} in the graph."
    return f"{n} {noun} in the graph."


def _tidy_sparql(q: Optional[str]) -> Optional[str]:
    if not q:
        return None
    lines = [re.sub(r"\s+#.*$", "", l.rstrip()) for l in q.strip().splitlines()]
    lines = [l for l in lines if l.strip() and not l.strip().upper().startswith("PREFIX")]
    if not lines:
        return None
    indent = min(len(l) - len(l.lstrip()) for l in lines)
    return "\n".join(l[indent:] for l in lines)


class _Tee(io.TextIOBase):
    """Write to the captured buffer and to the real stdout (server logs)."""

    def __init__(self, buf: io.StringIO, real):
        self.buf, self.real = buf, real

    def write(self, s):  # type: ignore[override]
        self.buf.write(s)
        self.real.write(s)
        return len(s)

    def flush(self):
        self.real.flush()


def answer(message: str) -> Dict[str, Any]:
    warm()
    assert STATE.responser is not None and STATE.graph is not None
    with _answer_lock:
        buf = io.StringIO()
        t0 = time.time()
        with contextlib.redirect_stdout(_Tee(buf, sys.__stdout__)):
            try:
                text = STATE.responser.generate_response(message, STATE.graph, WDT, WD)
            except Exception as exc:  # never leak a stack trace to the browser
                print(f"[api] error: {exc!r}")
                text = "Could not generate an answer. Please rephrase your question in a simple way."
        ms = (time.time() - t0) * 1000
        meta = dict(STATE.responser.last_meta)
        trace_raw = buf.getvalue()
    return build_reply(message, text, meta, trace_raw, ms)


# ---------- rate limit ----------

_hits: Dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


def _allow(ip: str) -> bool:
    now = time.time()
    with _hits_lock:
        q = _hits[ip]
        while q and q[0] < now - 60:
            q.popleft()
        if len(q) >= RATE_LIMIT_PER_MINUTE:
            return False
        q.append(now)
        if len(_hits) > 5000:
            _hits.clear()
        return True


# ---------- app ----------

class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)


def create_app(load_on_startup: bool = True) -> FastAPI:
    api = FastAPI(title="CineGraph API", docs_url=None, redoc_url=None)
    origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
    api.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["content-type"])

    if load_on_startup:
        @api.on_event("startup")
        def _startup() -> None:
            threading.Thread(target=warm, daemon=True).start()

    @api.get("/api/health")
    def health() -> Dict[str, Any]:
        ready = STATE.responser is not None
        return {
            "status": "ready" if ready else "loading",
            "triples": STATE.triples,
            "entities": len(STATE.ent_to_lbl),
            "embeddings": STATE.embeddings,
            "load_seconds": STATE.load_seconds,
        }

    def _catalog() -> Catalog:
        if STATE.catalog is None:
            raise HTTPException(status_code=503, detail="The graph is still loading.")
        return STATE.catalog

    @api.get("/api/showcase")
    def get_showcase() -> Dict[str, Any]:
        if STATE.catalog is None:
            return {"films": []}
        return {"films": STATE.catalog.wall(60)}

    @api.get("/api/films")
    def list_films(q: str = "", sort: str = "popular", offset: int = 0, limit: int = 60) -> Dict[str, Any]:
        return _catalog().list_films(q[:100], sort, max(0, offset), max(1, min(limit, 120)))

    @api.get("/api/search")
    def search(q: str = "") -> Dict[str, Any]:
        cat = _catalog()
        q = q[:100]
        return {"films": cat.list_films(q, "popular", 0, 8)["films"] if q.strip() else [], "people": cat.search_people(q, 8)}

    @api.get("/api/film/{film_qid}")
    def film(film_qid: str) -> Dict[str, Any]:
        data = _catalog().film(film_qid)
        if not data:
            raise HTTPException(status_code=404, detail="No film with this ID in the graph.")
        return data

    @api.get("/api/person/{person_qid}")
    def person(person_qid: str) -> Dict[str, Any]:
        data = _catalog().person(person_qid)
        if not data:
            raise HTTPException(status_code=404, detail="No person with this ID in the graph.")
        return data

    @api.get("/api/similar/{film_qid}")
    def similar(film_qid: str) -> Dict[str, Any]:
        cat = _catalog()
        row = cat.film_by_qid.get(film_qid)
        if not row or STATE.graph is None:
            raise HTTPException(status_code=404, detail="No film with this ID in the graph.")
        with _answer_lock:
            try:
                recs = recommend_movies(STATE.graph, [row["label"]], top_k=8)
            except Exception as exc:
                print(f"[api] similar failed: {exc!r}")
                recs = []
        out = []
        rec_uris = REC_LAST_RUN.get("recommendations") or {}
        for title, _score in recs:
            uri = rec_uris.get(title) or STATE.lbl_to_ent.get(title)
            q = _qid(str(uri)) if uri else None
            if q and q in cat.film_by_qid and q != film_qid:
                out.append(cat._public(cat.film_by_qid[q]))
        return {"films": out}

    @api.post("/api/chat")
    def chat(body: ChatIn, request: Request) -> Dict[str, Any]:
        fwd = request.headers.get("x-forwarded-for", "")
        ip = fwd.split(",")[0].strip() or (request.client.host if request.client else "?")
        if not _allow(ip):
            raise HTTPException(status_code=429, detail="Too many questions in a minute. Wait a moment and ask again.")
        message = body.message.strip()
        if not message:
            raise HTTPException(status_code=422, detail="Type a question first.")
        return answer(message)

    return api


app = create_app()
