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
# predicates that refer to an entity without making a film part of it: instance of, references
# work, cites work, different from, said to be the same as, see also, derivative work, inspired by
NOT_MEMBER = frozenset(URIRef("http://www.wikidata.org/prop/direct/" + p)
                       for p in ("P31", "P8371", "P2860", "P1889", "P460", "P1659", "P4969", "P941"))

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
# Kind from use when no class maps (many classes have no label, e.g. animation studio Q1107679):
# the object of a film's property, first matching rule wins.
USE_KIND = (
    (("P272", "P750"), "company"),
    (("P674",), "character"),
    (("P179",), "series"),
)
USE_KIND = tuple((tuple(URIRef("http://www.wikidata.org/prop/direct/" + p) for p in ps), k) for ps, k in USE_KIND)

# Ranking: score = 1000*kind_ok + tier + 500*year_ok + 10*ln(1+degree) (+ 50*ratio for fuzzy).
# A tier (exact 300 > span 200 > fuzzy 100) outweighs any popularity (10*ln(1+degree) < 150).
W_KIND = 1000.0
W_YEAR = 500.0
W_DEGREE = 10.0
TIER = {"exact": 300.0, "span": 200.0, "fuzzy": 100.0}
W_FUZZY = 50.0
# A subset match (all mention tokens inside a longer label) ranks just under a contained span.
SUBSET_PENALTY = 20.0
# A span of the mention that covers only part of its words loses up to this much, so a close
# typo match of the whole mention ("Tom Hanx" -> Tom Hanks) beats a bare "Tom".
PARTIAL_PENALTY = 150.0
# A kind read from use (no class) is a weaker claim: a classed entity of the same name and kind wins
# ("The Lord of the Rings" film trilogy over the novel that one film names as its series)
BY_USE_PENALTY = 90.0

MAX_NGRAM = 8
FUZZY_RATIO = 0.85
# Looser ratio when the words line up one to one, each starts with the same letter and is
# close on its own ("Tom Hanx", "Duvid Fancher", "pixer")
ALIGNED_RATIO = 0.8
ALIGNED_TOKEN_RATIO = 0.65   # "hanx"/"hanks" 0.67
MAX_PER_KEY = 60          # entities ranked per index key
MAX_RARE_TRIGRAMS = 8     # the rarest trigrams are often the misspelled ones: vote with more
MAX_POSTING = 4000        # trigram postings longer than this are too common to use
MAX_POSTING_FALLBACK = 20000
MIN_VOTE_GRAMS = 5
MAX_FUZZY_KEYS = 40
# A mention word used in at least this many labels is a real word, not a typo: it may change by one edit
# at most ("hank" -> "hanks", not "will" -> "willow"/"billy"), and a one-word mention made of it is not
# fuzzy-matched at all ("kids" -> "gkids")
KNOWN_WORD_LABELS = 3

STOP = frozenset("the a an of and in on at to for by with is was who what which when where how did does do "
                 "movie movies film films".split())

_SMART = str.maketrans({"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'", "‚": "'"})
_NON_ALNUM = re.compile(r"[^a-z0-9\s]")
_SPACES = re.compile(r"\s+")
_ARTICLE = re.compile(r"^(?:the|a|an)\s+")
_INITIAL = re.compile(r"^\s*a\s*\.")   # "A. Jones": an initial, not an article
_TAIL = re.compile(r"\s+(?:movies|films|movie|film)$")


def normalize(text: str) -> str:
    """Lower case, smart quotes plain, '&' -> 'and', '+' -> 'plus', accents folded, punctuation dropped,
    leading article dropped."""
    t = text.translate(_SMART).lower().replace("&", " and ").replace("+", " plus ")
    initial = bool(_INITIAL.match(t))
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("'", "")
    t = _NON_ALNUM.sub(" ", t)
    t = _SPACES.sub(" ", t).strip()
    return t if initial else _ARTICLE.sub("", t)


def _aligned(a: str, b: str) -> bool:
    """Same number of words, each pair with the same first letter and close on its own."""
    ta, tb = a.split(), b.split()
    if len(ta) != len(tb):
        return False
    for x, y in zip(ta, tb):
        if x == y:
            continue
        if x[0] != y[0] or len(x) < 4 or SequenceMatcher(None, x, y).ratio() < ALIGNED_TOKEN_RATIO:
            return False
    return True


def _one_edit(a: str, b: str) -> bool:
    """a and b differ by one insertion, deletion, substitution or swap of neighbours."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        return len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1
                                  and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


def _coverage(mention_key: str, label: str) -> float:
    """Share of the mention's content words that occur in the label."""
    toks = [t for t in mention_key.split() if t not in STOP]
    if not toks:
        return 1.0
    lt = set(normalize(label).split())
    return sum(t in lt for t in toks) / len(toks)


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
        self._by_use: set = set()     # entities whose kind came from use, not from a class
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
        kind = next((k for k in KIND_ORDER if k in kinds), None)
        if kind is None:
            kind = self._kind_by_use(uri)
            if kind != "other":
                self._by_use.add(uri)
        self._kind_cache[uri] = kind
        return kind

    def _kind_by_use(self, uri) -> str:
        """Kind of an entity whose classes map to none: from the film properties pointing at it."""
        for props, kind in USE_KIND:
            for p in props:
                if any(True for _ in self.g.subjects(p, uri)):
                    return kind
        return "other"

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
            if URIRef(str(uri)) in self._by_use:
                score -= BY_USE_PENALTY
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
        posts = sorted((len(self.tri[g]), g) for g in grams if g in self.tri)
        # rare trigrams first; common ones fill up to MIN_VOTE_GRAMS when a short or typo'd mention
        # has few rare ones left ("tom hanx")
        rare = [p for p in posts if p[0] <= MAX_POSTING]
        if len(rare) < MIN_VOTE_GRAMS:
            rare = [p for p in posts if p[0] <= MAX_POSTING_FALLBACK][:MIN_VOTE_GRAMS]
        posts = rare
        if not posts:
            return []
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
            if sm.real_quick_ratio() < ALIGNED_RATIO or sm.quick_ratio() < ALIGNED_RATIO:
                continue
            r = sm.ratio()
            if (r >= FUZZY_RATIO or (r >= ALIGNED_RATIO and len(key) >= 5 and _aligned(key, k))) \
                    and not self._other_word(key, k):
                scored.append((r, k))
        scored.sort(reverse=True)
        out = []
        for r, k in scored[:MAX_FUZZY_KEYS]:
            for u in self._pick(self.index[k]):
                out.append(self._cand(u, "fuzzy", r, want, year))
        return out

    def _other_word(self, key: str, label_key: str) -> bool:
        """The fuzzy label replaces a real word of the mention by another word, not a typo of it:
        "will smith" -> "willow smith" or "billy smith", "kids" -> "gkids". Only for word-aligned pairs."""
        ta, tb = key.split(), label_key.split()
        if len(ta) != len(tb):
            return False
        for x, y in zip(ta, tb):
            if x == y or len(self.tok.get(x, ())) < KNOWN_WORD_LABELS:
                continue
            if len(ta) == 1 or not _one_edit(x, y):
                return True
        return False

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
        partial = False
        if not ok(found):
            spans = self._spans(mention, want, year)
            key = normalize(mention)
            for c in spans:
                cov = _coverage(key, c.label)
                if cov < 1.0:
                    c.score -= PARTIAL_PENALTY * (1.0 - cov)
                    partial = True
            found += spans
        if not ok(found) and question:
            found += self._spans(question, want, year)
        if not ok(found) or (partial and not any(c.match == "exact" for c in found)):
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
        """Film URIs joined to a non-film entity by any predicate but a reference one, either direction."""
        uri = URIRef(str(uri))
        seen = {}
        for p, o in self.g.predicate_objects(uri):
            if p not in NOT_MEMBER and isinstance(o, URIRef) and o not in seen and self.kind_of(o) == "film":
                seen[o] = None
        for s, p in self.g.subject_predicates(uri):
            if p not in NOT_MEMBER and isinstance(s, URIRef) and s not in seen and self.kind_of(s) == "film":
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
