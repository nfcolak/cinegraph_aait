"""Browsable catalogue over the knowledge graph: every film and person, with all of their images.

Built once at startup from the same graph the agent uses plus images.json, so the web
interface can list all 12k films, open any film or person, and show every poster,
portrait and still the dataset holds (the agent itself keeps only the first image).
"""

from __future__ import annotations

import json
import random
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

import rdflib
from rdflib.namespace import RDFS

from core.data import IMAGE_MAP_PATH, WD, WDT

TMDB_BASE = "https://image.tmdb.org/t/p"
SCHEMA_DESC = rdflib.URIRef("http://schema.org/description")
TAG = rdflib.URIRef("http://ddis.ch/atai/tag")


def P(pid: str) -> rdflib.URIRef:
    return rdflib.URIRef(str(WDT) + pid)


P31, P345, P577, P161 = P("P31"), P("P345"), P("P577"), P("P161")
FILM = rdflib.URIRef(str(WD) + "Q11424")
HUMAN = rdflib.URIRef(str(WD) + "Q5")

# Film facts shown on a film page, in reading order: (property, label, links to people)
FILM_FACTS = [
    ("P57", "Director", True),
    ("P58", "Screenwriter", True),
    ("P86", "Composer", True),
    ("P344", "Cinematography", True),
    ("P1040", "Editing", True),
    ("P162", "Producer", True),
    ("P2515", "Costume design", True),
    ("P2554", "Production design", True),
    ("P272", "Production company", False),
    ("P750", "Distributor", False),
    ("P495", "Country", False),
    ("P364", "Original language", False),
    ("P144", "Based on", False),
    ("P840", "Set in", False),
    ("P915", "Filmed in", False),
    ("P166", "Awards", False),
    ("P1411", "Nominations", False),
]

# Roles that place a person in a film's credits, for filmographies
ROLES = [("P57", "Director"), ("P161", "Actor"), ("P58", "Screenwriter"), ("P86", "Composer"), ("P162", "Producer"),
         ("P344", "Cinematographer"), ("P1040", "Editor")]

PERSON_FACTS = [("P106", "Occupation"), ("P27", "Citizenship"), ("P19", "Born in"), ("P20", "Died in"), ("P166", "Awards")]


def tmdb(path: str, size: str) -> str:
    name = path.rsplit("/", 1)[-1]
    if "." not in name:
        name += ".jpg"
    return f"{TMDB_BASE}/{size}/{name}"


def qid(uri: Any) -> Optional[str]:
    s = str(uri)
    return s[len(str(WD)):] if s.startswith(str(WD)) else None


class Catalog:
    def __init__(self, graph: rdflib.Graph, ent_to_lbl: Dict[Any, str], ratings: Dict[str, float]):
        self.g = graph
        self.lbl = ent_to_lbl
        self.ratings = ratings
        self.images: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: {"poster": [], "backdrop": [], "profile": []})
        self._load_images()
        self.films: List[Dict[str, Any]] = []
        self.film_by_qid: Dict[str, Dict[str, Any]] = {}
        self._build_films()
        self.people: List[Dict[str, Any]] = []
        self.person_credits: Dict[str, int] = {}
        self._build_people()

    # ---------- build ----------

    def _load_images(self) -> None:
        with open(IMAGE_MAP_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            path, kind = item.get("img"), item.get("type")
            if not path or kind not in ("poster", "backdrop", "profile"):
                continue
            ids = item.get("cast", []) if kind == "profile" else item.get("movie", [])
            for i in ids:
                self.images[i][kind].append(path)
            if kind == "backdrop":  # a still also belongs to the people in it
                for nm in item.get("cast", []):
                    self.images[nm]["backdrop"].append(path)
        del data

    def _label(self, uri: Any) -> Optional[str]:
        ref = uri if isinstance(uri, rdflib.URIRef) else rdflib.URIRef(str(uri))
        return self.lbl.get(ref)

    def _imdb(self, ref: rdflib.URIRef) -> Optional[str]:
        v = self.g.value(ref, P345)
        return str(v) if v else None

    def _build_films(self) -> None:
        for ref in set(self.g.subjects(P31, FILM)):
            label = self._label(ref)
            if not label:
                continue
            imdb = self._imdb(ref)
            imgs = self.images.get(imdb) if imdb else None
            date = self.g.value(ref, P577)
            row = {
                "qid": qid(ref),
                "label": label,
                "year": str(date)[:4] if date else None,
                "image": tmdb(imgs["poster"][0], "w342") if imgs and imgs["poster"] else None,
                "rating": round(self.ratings[str(ref)], 2) if str(ref) in self.ratings else None,
                # TMDB keeps more artwork for widely seen films, so image count is a usable popularity proxy
                "_pop": (len(imgs["poster"]) + len(imgs["backdrop"]) if imgs else 0) + sum(1 for _ in self.g.objects(ref, P161)) / 4,
                "_key": label.lower(),
                "_sort": re.sub(r"^[^0-9a-z]+", "", label.lower()) or label.lower(),
            }
            self.films.append(row)
            self.film_by_qid[row["qid"]] = row
        self.films.sort(key=lambda r: (-r["_pop"], r["_key"]))

    def _build_people(self) -> None:
        for ref in set(self.g.subjects(P31, HUMAN)):
            label = self._label(ref)
            if not label:
                continue
            imdb = self._imdb(ref)
            imgs = self.images.get(imdb) if imdb else None
            self.people.append({
                "qid": qid(ref),
                "label": label,
                "image": tmdb(imgs["profile"][0], "w185") if imgs and imgs["profile"] else None,
                "_credits": sum(1 for p, _ in ROLES for _ in self.g.subjects(P(p), ref)),
                "_key": label.lower(),
            })
        self.people.sort(key=lambda r: (-r["_credits"], r["_key"]))
        self.person_credits = {r["qid"]: r["_credits"] for r in self.people}

    # ---------- queries ----------

    @staticmethod
    def _public(row: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in row.items() if not k.startswith("_")}

    def list_films(self, q: str = "", sort: str = "popular", offset: int = 0, limit: int = 60) -> Dict[str, Any]:
        rows = self.films
        q = q.strip().lower()
        if q:
            starts = [r for r in rows if r["_key"].startswith(q)]
            inner = [r for r in rows if q in r["_key"] and not r["_key"].startswith(q)]
            rows = starts + inner
        if sort == "rating":
            rows = sorted(rows, key=lambda r: (r["rating"] is None, -(r["rating"] or 0), -r["_pop"]))
        elif sort == "newest":
            rows = sorted(rows, key=lambda r: (r["year"] is None, -(int(r["year"]) if r["year"] else 0), -r["_pop"]))
        elif sort == "oldest":
            rows = sorted(rows, key=lambda r: (r["year"] is None, int(r["year"]) if r["year"] else 0, -r["_pop"]))
        elif sort == "title":
            rows = sorted(rows, key=lambda r: r["_sort"])
        page = rows[offset: offset + limit]
        return {"total": len(rows), "offset": offset, "films": [self._public(r) for r in page]}

    def search_people(self, q: str, limit: int = 12) -> List[Dict[str, Any]]:
        q = q.strip().lower()
        if len(q) < 2:
            return []
        starts = [r for r in self.people if r["_key"].startswith(q) or f" {q}" in r["_key"]]
        inner = [r for r in self.people if q in r["_key"] and r not in starts[:limit]] if len(starts) < limit else []
        return [self._public(r) for r in (starts + inner)[:limit]]

    def linked_films(self, uri: Any) -> List[Dict[str, Any]]:
        """Films joined to a non-film entity by any edge, either direction (character P674/P1441, series P179 ...)."""
        ref = uri if isinstance(uri, rdflib.URIRef) else rdflib.URIRef(str(uri))
        seen: Dict[str, Dict[str, Any]] = {}
        for o in self.g.objects(ref, None):
            row = self.film_by_qid.get(qid(o) or "")
            if row:
                seen[row["qid"]] = row
        for s in self.g.subjects(None, ref):
            row = self.film_by_qid.get(qid(s) or "")
            if row:
                seen[row["qid"]] = row
        rows = sorted(seen.values(), key=lambda r: (r["year"] is None, r["year"] or "", r["_key"]))
        return [self._public(r) for r in rows]

    def fact_across(self, films: List[Dict[str, Any]], pid: str) -> List[Dict[str, Any]]:
        """Values of one property over several films: [{label, qid, films: [titles]}], most frequent first."""
        agg: Dict[str, Dict[str, Any]] = {}
        for f in films:
            ref = rdflib.URIRef(str(WD) + f["qid"])
            for o in self.g.objects(ref, P(pid)):
                label = self._label(o) if isinstance(o, rdflib.URIRef) else str(o)
                if not label:
                    continue
                item = agg.setdefault(label, {"label": label, "qid": qid(o), "films": []})
                item["films"].append(f["label"])
        return sorted(agg.values(), key=lambda v: -len(v["films"]))

    def wall(self, n: int = 60) -> List[Dict[str, Any]]:
        """A random sample of well-known films with posters, different on every call."""
        pool = [r for r in self.films[:2500] if r["image"]]
        return [self._public(r) for r in random.sample(pool, min(n, len(pool)))]

    def _person_ref(self, ref: rdflib.URIRef) -> Dict[str, Any]:
        imdb = self._imdb(ref)
        imgs = self.images.get(imdb) if imdb else None
        return {"qid": qid(ref), "label": self._label(ref) or qid(ref),
                "image": tmdb(imgs["profile"][0], "w185") if imgs and imgs["profile"] else None}

    def _values(self, ref: rdflib.URIRef, pid: str, people: bool) -> List[Dict[str, Any]]:
        out = []
        for o in self.g.objects(ref, P(pid)):
            if isinstance(o, rdflib.URIRef):
                label = self._label(o)
                if not label:
                    continue
                item: Dict[str, Any] = {"label": label}
                if people and (o, P31, HUMAN) in self.g:
                    item.update(self._person_ref(o))
                out.append(item)
            else:
                out.append({"label": str(o)})
        return sorted(out, key=lambda v: v["label"])

    def film(self, film_qid: str) -> Optional[Dict[str, Any]]:
        row = self.film_by_qid.get(film_qid)
        if not row:
            return None
        ref = rdflib.URIRef(str(WD) + film_qid)
        imdb = self._imdb(ref)
        imgs = self.images.get(imdb, {"poster": [], "backdrop": [], "profile": []}) if imdb else {"poster": [], "backdrop": [], "profile": []}
        date = self.g.value(ref, P577)
        facts = []
        for pid, name, people in FILM_FACTS:
            vals = self._values(ref, pid, people)
            if vals:
                facts.append({"property": pid, "name": name, "values": vals[:12], "more": max(0, len(vals) - 12)})
        cast = [self._person_ref(o) for o in self.g.objects(ref, P161) if isinstance(o, rdflib.URIRef) and self._label(o)]
        cast.sort(key=lambda c: (c["image"] is None, -self.person_credits.get(c["qid"], 0), c["label"]))
        genres = [v["label"] for v in self._values(ref, "P136", False)]
        desc = self.g.value(ref, SCHEMA_DESC)
        tags = sorted({str(t).replace("_", " ") for t in self.g.objects(ref, TAG)})
        return {
            **self._public(row),
            "imdb": imdb,
            "date": str(date)[:10] if date else None,
            "description": str(desc) if desc else None,
            "genres": genres,
            "tags": tags[:16],
            "facts": facts,
            "cast": cast[:30],
            "cast_total": len(cast),
            "posters": [tmdb(p, "w342") for p in imgs["poster"][:40]],
            "posters_total": len(imgs["poster"]),
            "stills": [tmdb(p, "w780") for p in imgs["backdrop"][:40]],
            "stills_total": len(imgs["backdrop"]),
            "backdrop": tmdb(imgs["backdrop"][0], "w1280") if imgs["backdrop"] else None,
        }

    def person(self, person_qid: str) -> Optional[Dict[str, Any]]:
        ref = rdflib.URIRef(str(WD) + person_qid)
        if (ref, P31, HUMAN) not in self.g or not self._label(ref):
            return None
        imdb = self._imdb(ref)
        imgs = self.images.get(imdb, {"poster": [], "backdrop": [], "profile": []}) if imdb else {"poster": [], "backdrop": [], "profile": []}
        credits = []
        for pid, role in ROLES:
            films = [self._public(self.film_by_qid[q]) for q in (qid(s) for s in self.g.subjects(P(pid), ref)) if q in self.film_by_qid]
            if films:
                films.sort(key=lambda f: f["year"] or "0", reverse=True)
                credits.append({"role": role, "property": pid, "films": films})
        credits.sort(key=lambda c: -len(c["films"]))
        facts = []
        for pid, name in PERSON_FACTS:
            vals = [v["label"] for v in self._values(ref, pid, False)]
            if vals:
                facts.append({"property": pid, "name": name, "values": vals[:8]})
        desc = self.g.value(ref, SCHEMA_DESC)
        return {
            "qid": person_qid,
            "label": self._label(ref),
            "imdb": imdb,
            "description": str(desc) if desc else None,
            "image": tmdb(imgs["profile"][0], "h632") if imgs["profile"] else None,
            "facts": facts,
            "credits": credits,
            "portraits": [tmdb(p, "w185") for p in imgs["profile"][:30]],
            "portraits_total": len(imgs["profile"]),
            "stills": [tmdb(p, "w780") for p in imgs["backdrop"][:30]],
            "stills_total": len(imgs["backdrop"]),
        }
