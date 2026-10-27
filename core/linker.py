# linker.py
# Entity linker: maps a subject mention to graph entities by kind, exactness, year and popularity.

import math
import re
import unicodedata
from array import array
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher

from rdflib import URIRef

KINDS = ("film", "person", "character", "series", "company", "other")

WD = "http://www.wikidata.org/entity/"
P31 = URIRef("http://www.wikidata.org/prop/direct/P31")
P577 = URIRef("http://www.wikidata.org/prop/direct/P577")
Q_HUMAN = URIRef(WD + "Q5")

# P31 class -> kind, from the P31 counts of data/graph.nt (counts in brackets).
# Labels marked (n/a) have no rdfs:label in the graph; the name is the Wikidata one.
CLASS_KIND = {
    # film
    "Q11424": "film",        # film [12245]
    "Q202866": "film",       # animated film [377]
    "Q24862": "film",        # short film [221]
    "Q506240": "film",       # television film [213]
    "Q17517379": "film",     # animated short film [97]
    "Q226730": "film",       # silent film [39]
    "Q20650540": "film",     # anime film [23]
    "Q61283808": "film",     # Star Trek film [13]
    "Q917641": "film",       # open-source film [2]
    "Q104840802": "film",    # film remake [3]
    "Q622548": "film",       # parody film [2]
    "Q2484376": "film",      # thriller film [1]
    "Q17123180": "film",     # sequel film [2]
    "Q118189123": "film",    # animated film reboot [1]
    "Q112158242": "film",    # Tom and Jerry film [1]
    "Q52207399": "film",     # film based on a novel [1]
    "Q52162262": "film",     # film based on literature [1]
    "Q24869": "film",        # feature film (n/a, 0 in this graph)
    # person
    "Q5": "person",          # human (n/a) [85854]
    # character
    "Q15632617": "character",  # fictional human (n/a) [4628]
    "Q15773347": "character",  # film character (n/a) [3982]
    "Q15711870": "character",  # fictional character, samples Jaq/Jim Crow (n/a) [1610]
    "Q3658341": "character",   # literary character (n/a) [1136]
    "Q15773317": "character",  # television character (n/a) [550]
    "Q1114461": "character",   # comics character (n/a) [429]
    "Q95074": "character",     # character (n/a) [106]
    # series
    "Q24856": "series",      # film series [364]
    "Q5398426": "series",    # television series [245]
    "Q196600": "series",     # media franchise [217]
    "Q117467246": "series",  # animated television series [76]
    "Q13593818": "series",   # film trilogy [77]
    "Q1259759": "series",    # miniseries [46]
    "Q526877": "series",     # web series [7]
    "Q559618": "series",     # fictional universe (n/a), samples "Top Gun universe" [224]
    # company
    "Q1762059": "company",   # film production company [1388]
    "Q4830453": "company",   # business (n/a) [623]
    "Q368290": "company",    # film distributor (n/a), samples Broad Green Pictures [254]
    "Q11396960": "company",  # production company [171]
    "Q18127": "company",     # record label [76]
}
# Precedence when an entity has several P31 classes.
KIND_ORDER = ("film", "person", "character", "series", "company")
# Class labels containing these words map to a kind when the class is not in CLASS_KIND.
LABEL_WORDS = (("character", "character"), ("series", "series"), ("franchise", "series"),
               ("company", "company"), ("studio", "company"))

# Ranking: score = 1000*kind_ok + tier + 500*year_ok + 10*ln(1+degree) (+ 50*ratio for fuzzy).
# A tier (exact 300 > span 200 > fuzzy 100) outweighs any popularity (10*ln(1+degree) < 150).
W_KIND = 1000.0
W_YEAR = 500.0
W_DEGREE = 10.0
TIER = {"exact": 300.0, "span": 200.0, "fuzzy": 100.0}
W_FUZZY = 50.0
# A subset match (all mention tokens inside a longer label) ranks just under a contained span.
SUBSET_PENALTY = 20.0

MAX_NGRAM = 8
FUZZY_RATIO = 0.85
MAX_PER_KEY = 60          # entities ranked per index key
MAX_RARE_TRIGRAMS = 4
MAX_POSTING = 4000        # trigram postings longer than this are too common to use
MAX_FUZZY_KEYS = 40

STOP = frozenset("the a an of and in on at to for by with is was who what which when where how did does do "
                 "movie movies film films".split())

_SMART = str.maketrans({"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'", "‚": "'"})
_NON_ALNUM = re.compile(r"[^a-z0-9\s]")
_SPACES = re.compile(r"\s+")
_ARTICLE = re.compile(r"^(?:the|a|an)\s+")
_TAIL = re.compile(r"\s+(?:movies|films|movie|film)$")


def normalize(text: str) -> str:
    """Lower case, smart quotes plain, '&' -> 'and', accents folded, punctuation dropped, leading article dropped."""
    t = text.translate(_SMART).lower().replace("&", " and ")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("'", "")
    t = _NON_ALNUM.sub(" ", t)
    t = _SPACES.sub(" ", t).strip()
    return _ARTICLE.sub("", t)


def _variants(key: str):
    """Key plus forms with a trailing film word or plural 's' removed."""
    out = [key]
    k = _TAIL.sub("", key)
    if k and k != key:
        out.append(k)
    for base in list(out):
        if len(base) > 3 and base.endswith("s"):
            out.append(base[:-1])
    seen, res = set(), []
    for v in out:
        if v and v not in seen:
            seen.add(v)
            res.append(v)
    return res


@dataclass
class Candidate:
    uri: str
    qid: str
    label: str
    kind: str              # one of KINDS
    year: int | None       # films: year of the earliest P577, else None
    degree: int            # number of triples the entity takes part in (subject or object)
    match: str             # "exact" | "span" | "fuzzy"
    score: float


class EntityLinker:
    def __init__(self, graph, ent_to_lbl: dict):
        self.g = graph
        self.lbl = ent_to_lbl
        self._kind_cache: dict = {}
        self._class_kind: dict = {}
        self._info_cache: dict = {}
        self._build()

    # ---- index ----
    def _build(self):
        index = defaultdict(list)
        for uri, label in self.lbl.items():
            key = normalize(label)
            if key:
                index[key].append(uri)
        self.index = dict(index)
        self.keys = list(self.index)
        tri = defaultdict(lambda: array("I"))
        tok = defaultdict(lambda: array("I"))
        for i, key in enumerate(self.keys):
            if len(key) >= 4:
                for t in {key[j:j + 3] for j in range(len(key) - 2)}:
                    tri[t].append(i)
            for t in set(key.split()):
                if t not in STOP:
                    tok[t].append(i)
        self.tri = dict(tri)
        self.tok = dict(tok)
        # surname index over persons (labels of 2-4 tokens): last token -> uris
        sur = defaultdict(list)
        for s in self.g.subjects(P31, Q_HUMAN):
            label = self.lbl.get(s)
            if not label:
                continue
            parts = normalize(label).split()
            if 2 <= len(parts) <= 4:
                sur[parts[-1]].append(s)
        self.surname = dict(sur)

    # ---- entity facts ----
    def _kind_of_class(self, cls) -> str | None:
        qid = str(cls).rsplit("/", 1)[-1]
        k = CLASS_KIND.get(qid)
        if k:
            return k
        if cls in self._class_kind:
            return self._class_kind[cls]
        label = (self.lbl.get(cls) or "").lower()
        found = None
        for word, kind in LABEL_WORDS:
            if word in label:
                found = kind
                break
        self._class_kind[cls] = found
        return found

    def kind_of(self, uri) -> str:
        uri = URIRef(str(uri))
        cached = self._kind_cache.get(uri)
        if cached is not None:
            return cached
        kinds = {self._kind_of_class(c) for c in self.g.objects(uri, P31)}
        kind = next((k for k in KIND_ORDER if k in kinds), "other")
        self._kind_cache[uri] = kind
        return kind

    def _year(self, uri) -> int | None:
        years = []
        for o in self.g.objects(uri, P577):
            m = re.match(r"-?\d{4}", str(o))
            if m:
                years.append(int(m.group()))
        return min(years) if years else None

    def _info(self, uri):
        """(kind, year, degree) of an entity, cached."""
        hit = self._info_cache.get(uri)
        if hit is None:
            kind = self.kind_of(uri)
            year = self._year(uri) if kind == "film" else None
            degree = sum(1 for _ in self.g.predicate_objects(uri)) + sum(1 for _ in self.g.subject_predicates(uri))
            hit = (kind, year, degree)
            self._info_cache[uri] = hit
        return hit

    def _cand(self, uri, match, ratio, want, year, penalty=0.0) -> Candidate:
        kind, fyear, degree = self._info(uri)
        score = TIER[match] - penalty + W_DEGREE * math.log1p(degree)
        if want and kind in want:
            score += W_KIND
        if year is not None and fyear == year:
            score += W_YEAR
        if match == "fuzzy":
            score += W_FUZZY * ratio
        label = self.lbl.get(uri, "")
        return Candidate(uri=str(uri), qid=str(uri).rsplit("/", 1)[-1], label=label, kind=kind,
                         year=fyear, degree=degree, match=match, score=score)

    def _pick(self, uris):
        return uris[:MAX_PER_KEY] if len(uris) > MAX_PER_KEY else uris

    # ---- matching tiers ----
    def _exact(self, mention, want, year):
        out = []
        for v in _variants(normalize(mention)):
            for u in self._pick(self.index.get(v, ())):
                out.append(self._cand(u, "exact", 1.0, want, year))
        return out

    def _spans(self, text, want, year):
        """Longest label n-grams contained in text; shorter n-grams only when longer ones give no wanted kind."""
        toks = normalize(text).split()
        out = []
        for n in range(min(MAX_NGRAM, len(toks)), 0, -1):
            level = []
            for i in range(len(toks) - n + 1):
                gram = toks[i:i + n]
                if n == 1 and gram[0] in STOP:
                    continue
                if all(t in STOP for t in gram):
                    continue
                for u in self._pick(self.index.get(" ".join(gram), ())):
                    level.append(self._cand(u, "span", 1.0, want, year))
            if level:
                out.extend(level)
                if not want or any(c.kind in want for c in level):
                    break
        return out

    def _subset(self, mention, want, year):
        """Labels that hold every mention token (Jack Sparrow -> Captain Jack Sparrow)."""
        toks = [t for t in normalize(mention).split() if t not in STOP]
        if len(toks) < 2:
            return []
        lists = [self.tok.get(t) for t in toks]
        if any(l is None for l in lists):
            return []
        rare = min(lists, key=len)
        if len(rare) > 20000:
            return []
        need = set(toks)
        out = []
        for i in rare:
            key = self.keys[i]
            kt = key.split()
            if need <= set(kt) and len(kt) <= len(toks) + 4:
                for u in self._pick(self.index[key]):
                    out.append(self._cand(u, "span", 1.0, want, year, penalty=SUBSET_PENALTY))
            if len(out) > 400:
                break
        return out

    def _surname(self, mention, want, year):
        toks = normalize(mention).split()
        if len(toks) != 1 or not want or "person" not in want:
            return []
        uris = self.surname.get(toks[0], ())
        if len(uris) > 3000:
            uris = uris[:3000]
        return [self._cand(u, "span", 1.0, want, year) for u in uris]

    def _fuzzy(self, mention, want, year):
        key = normalize(mention)
        if len(key) < 4:
            return []
        grams = {key[j:j + 3] for j in range(len(key) - 2)}
        posts = [(len(self.tri[g]), g) for g in grams if g in self.tri and len(self.tri[g]) <= MAX_POSTING]
        if not posts:
            return []
        posts.sort()
        votes = defaultdict(int)
        for _, g in posts[:MAX_RARE_TRIGRAMS]:
            for i in self.tri[g]:
                votes[i] += 1
        # rank by shared trigrams among all of the mention's trigrams
        top = sorted(votes, key=lambda i: -votes[i])[:MAX_FUZZY_KEYS * 4]
        scored = []
        sm = SequenceMatcher(autojunk=False)
        sm.set_seq2(key)
        for i in top:
            k = self.keys[i]
            if abs(len(k) - len(key)) > max(3, len(key) // 4):
                continue
            sm.set_seq1(k)
            if sm.real_quick_ratio() < FUZZY_RATIO or sm.quick_ratio() < FUZZY_RATIO:
                continue
            r = sm.ratio()
            if r >= FUZZY_RATIO:
                scored.append((r, k))
        scored.sort(reverse=True)
        out = []
        for r, k in scored[:MAX_FUZZY_KEYS]:
            for u in self._pick(self.index[k]):
                out.append(self._cand(u, "fuzzy", r, want, year))
        return out

    # ---- public API ----
    def link(self, mention: str, want: set | None = None, year: int | None = None,
             question: str | None = None, limit: int = 5) -> list[Candidate]:
        if not mention or not normalize(mention):
            return []
        found = self._exact(mention, want, year)
        ok = lambda cs: not want or any(c.kind in want for c in cs)
        if not ok(found):
            found += self._surname(mention, want, year)
        if not ok(found):
            found += self._subset(mention, want, year)
        if not ok(found):
            found += self._spans(mention, want, year)
        if not ok(found) and question:
            found += self._spans(question, want, year)
        if not ok(found):
            found += self._fuzzy(mention, want, year)
        return self._rank(found, limit)

    def scan(self, question: str, want: set | None = None, limit: int = 5) -> list[Candidate]:
        return self._rank(self._spans(question, want, None), limit)

    @staticmethod
    def _rank(cands, limit):
        best = {}
        for c in cands:
            if c.uri not in best or c.score > best[c.uri].score:
                best[c.uri] = c
        return sorted(best.values(), key=lambda c: (-c.score, c.label))[:limit]

    def films_of_entity(self, uri) -> list[str]:
        """Film URIs joined to a non-film entity by any predicate, either direction."""
        uri = URIRef(str(uri))
        seen = {}
        for p, o in self.g.predicate_objects(uri):
            if p != P31 and isinstance(o, URIRef) and o not in seen and self.kind_of(o) == "film":
                seen[o] = None
        for s, p in self.g.subject_predicates(uri):
            if p != P31 and isinstance(s, URIRef) and s not in seen and self.kind_of(s) == "film":
                seen[s] = None
        films = list(seen)
        films.sort(key=lambda f: (self._year(f) is None, self._year(f) or 0, self.lbl.get(f, "")))
        return [str(f) for f in films]

    def alternatives(self, best: Candidate, limit: int = 5) -> list[Candidate]:
        """Other entities with the same normalized label and kind as best."""
        key = normalize(best.label)
        out = []
        for u in self.index.get(key, ()):
            if str(u) == best.uri:
                continue
            c = self._cand(u, "exact", 1.0, {best.kind}, None)
            if c.kind == best.kind:
                out.append(c)
        return self._rank(out, limit)


_CACHE: dict = {}


def get_linker(graph, ent_to_lbl: dict) -> EntityLinker:
    linker = _CACHE.get(id(graph))
    if linker is None:
        linker = EntityLinker(graph, ent_to_lbl)
        _CACHE[id(graph)] = linker
    return linker


def peek_linker(graph) -> EntityLinker | None:
    """The linker already built for this graph, or None (callers without the label map)."""
    return _CACHE.get(id(graph))
