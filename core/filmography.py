# filmography.py
# Fallback answers for questions that name a person, company, character, series or film but whose
# wording the intent parser does not cover: "In which movies Daniel Radcliffe played?", "Daniel
# Radcliffe films", "Tom Hanks filmography", "Who is Daniel Radcliffe?", "Tell me about Inception",
# "Which movies did Emma Watson and Daniel Radcliffe play in together?", "Spielberg films from the
# 80s", "How many movies did Kubrick direct?", "Who played Gandalf?", "Sherlock Holmes movies".
# Pure graph lookups through the entity linker; no embeddings, no guessing.

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import rdflib

from core.intent import _DECADE_WORDS, year_span
from core.linker import STOP, normalize

WDT = "http://www.wikidata.org/prop/direct/"
DESCRIPTION = rdflib.URIRef("http://schema.org/description")
P31 = rdflib.URIRef(WDT + "P31")
P136 = rdflib.URIRef(WDT + "P136")
P161 = rdflib.URIRef(WDT + "P161")
P175 = rdflib.URIRef(WDT + "P175")   # performer: the actor behind a character

# (role label, property) in the order roles are listed
ROLES = [
    ("cast member", "P161"),
    ("director", "P57"),
    ("screenwriter", "P58"),
    ("composer", "P86"),
    ("producer", "P162"),
    ("production company", "P272"),
    ("cinematographer", "P344"),
    ("distributed by", "P750"),
]
ROLE_PROP = dict(ROLES)
# a company "makes", "produces" or "directs" through P272
COMPANY_ROLE = {"director": "production company", "producer": "production company",
                "cast member": None, "screenwriter": None, "composer": None, "cinematographer": None}

# Role named by the question's wording; None = no role word (filmography, "X movies", "who is X")
_ROLE_CUES = [
    (re.compile(r"\b(?:play(?:s|ed|ing)?|act(?:s|ed|ing|or|ors|ress|resses)?|starr?(?:s|ed|ing)?|appear(?:s|ed|ing)?|"
                r"featur(?:e|es|ed|ing)|cast|roles?|been\s+in|was\s+in|were\s+in|is\s+in|are\s+in)\b", re.I),
     "cast member"),
    (re.compile(r"\b(?:direct(?:s|ed|ing|or|ors)?|helm(?:s|ed)?|made|makes?|making)\b|"
                r"\b(?:movies?|films?|works?)\s+by\b", re.I), "director"),
    (re.compile(r"\b(?:wr[io]te|writes?|written|writing|writers?|screenplays?|scripts?)\b", re.I), "screenwriter"),
    (re.compile(r"\b(?:compos(?:e|es|ed|ing|er|ers)|scor(?:e|es|ed|ing)|music|soundtracks?)\b", re.I), "composer"),
    (re.compile(r"\b(?:produc(?:e|es|ed|ing|er|ers))\b", re.I), "producer"),
    (re.compile(r"\b(?:shot|shoots?|shooting|cinematograph\w*|filmed)\b", re.I), "cinematographer"),
    (re.compile(r"\b(?:distribut\w*)\b", re.I), "distributed by"),
]
_TOGETHER = re.compile(r"\b(?:together|both|with\s+each\s+other|in\s+common|same\s+(?:movies?|films?))\b", re.I)
_ABOUT = re.compile(r"^\s*(?:who|what)\s+(?:is|was|are|were)\b|\b(?:tell\s+me\s+about|about|info(?:rmation)?\s+(?:on|about)|"
                    r"describe|overview|summary|bio(?:graphy)?)\b", re.I)
_COUNT = re.compile(r"\b(?:how\s+many|number\s+of|count\s+of|how\s+much)\b", re.I)
# "Who played Gandalf?", "actor of Darth Vader": the cast behind a character, not its films
_WHO_PLAYED = re.compile(r"\bwho\s+(?:play(?:s|ed)?|portray(?:s|ed)?|voice[sd]?|act(?:s|ed)?|starr?(?:s|ed))\b|"
                         r"\b(?:actors?|actress(?:es)?|played\s+by|portrayed\s+by|voiced\s+by|cast)\b", re.I)

# Genre words of a question -> stems searched in the labels of a film's genres (P136) and classes
GENRES = [
    (re.compile(r"\brom-?coms?\b|\bromantic\s+comed(?:y|ies)\b", re.I), "romantic comedy", ("romantic comedy",)),
    (re.compile(r"\bcomed(?:y|ies)\b|\bfunny\b", re.I), "comedy", ("comedy",)),
    (re.compile(r"\bdramas?\b", re.I), "drama", ("drama",)),
    (re.compile(r"\bcrime\b", re.I), "crime", ("crime",)),
    (re.compile(r"\bthrillers?\b", re.I), "thriller", ("thriller",)),
    (re.compile(r"\bhorrors?\b|\bscary\b", re.I), "horror", ("horror",)),
    (re.compile(r"\bsci-?fi\b|\bscience[\s-]fiction\b|\bscifi\b", re.I), "science fiction", ("science fiction",)),
    (re.compile(r"\bfantasy\b|\bfantasies\b", re.I), "fantasy", ("fantasy",)),
    (re.compile(r"\bwesterns?\b", re.I), "western", ("western",)),
    (re.compile(r"\bmyster(?:y|ies)\b", re.I), "mystery", ("mystery",)),
    (re.compile(r"\baction\b", re.I), "action", ("action",)),
    (re.compile(r"\banimated\b|\banimation\b|\bcartoons?\b", re.I), "animated", ("animat",)),
    (re.compile(r"\bmusicals?\b", re.I), "musical", ("musical",)),
    (re.compile(r"\bromance\b|\bromantic\b|\bromances\b|\blove\s+stor(?:y|ies)\b", re.I), "romance",
     ("romance", "romantic")),
    (re.compile(r"\bwar\s+(?:movies?|films?|dramas?)\b", re.I), "war", ("war film",)),
    (re.compile(r"\bdocumentar(?:y|ies)\b", re.I), "documentary", ("documentary",)),
    (re.compile(r"\badventures?\b", re.I), "adventure", ("adventure",)),
    (re.compile(r"\bbiopics?\b|\bbiograph(?:y|ies|ical)\b", re.I), "biographical", ("biograph",)),
    (re.compile(r"\bsuperheroe?s?\b", re.I), "superhero", ("superhero",)),
    (re.compile(r"\bnoirs?\b", re.I), "noir", ("noir",)),
    (re.compile(r"\bspy\b|\bespionage\b", re.I), "spy", ("spy",)),
    (re.compile(r"\bfamily\s+(?:movies?|films?)\b|\bkids?\s+(?:movies?|films?)\b", re.I), "family",
     ("family", "children")),
]

# Year ranges are read by core.intent.year_span (one reader for parser, filmography and recommender)

# words removed before linking the remainder of the question as a name
_NOISE = re.compile(
    r"\b(?:in|on|of|for|by|with|which|what|who|whom|whose|where|when|how|did|does|do|has|have|had|is|are|was|were|been|be|"
    r"the|a|an|all|any|some|list|show|me|tell|give|name|please|movies?|films?|filmography|works?|career|credits?|roles?|"
    r"play(?:s|ed|ing)?|act(?:s|ed|ing)?|starr?(?:s|ed|ing)?|appear(?:s|ed|ing)?|featur(?:e|es|ed|ing)|direct(?:s|ed|ing)?|"
    r"made|make|wr[io]te|written|compos(?:e|ed)|scor(?:e|ed)|produc(?:e|ed)|shot|together|both|and|about|info|known|"
    r"famous|popular|best|other|else|also|ever|so\s+far|until\s+now|many|much|number|count|there|them|it|its|"
    r"good|great|greatest|top|nice|cool|awesome|decent|fun|underrated|new|newest|old|oldest|classic|favou?rite|"
    r"recent|latest|worst|"
    r"just|curious|thanks?|thank\s+you|hey|hi|hello|pls|plz|can|could|you|u|i|my|"
    r"released?|after|before|since|between|until|till|from|to|during|decade|era|early|mid|late|year|years|"
    r"soundtracks?|music|scores?|comedies|dramas|westerns|thrillers|musicals|mysteries|"
    r"\d+s?|" + "|".join(_DECADE_WORDS) + r")\b", re.I)

MAX_LISTED = 6
MAX_CAST = 6
# a one-word surname links only to a person with at least this many credited films, when the
# word occurs in at most this many labels or is written with a capital (a name, not a common word)
SURNAME_MIN_FILMS = 5
SURNAME_MAX_LABELS = 40
SURNAME_TYPO_MIN = 6   # a surname typo is corrected from this length on
# a span inside a longer label of these kinds is not a person ("Indiana Jones" is not "A. Jones")
_CONTAINER_KINDS = ("character", "series", "film")
# capitalized words that open a sentence or a question, never a name
_LEAD_WORDS = frozenset("who what which when where how did does do is are was were tell show give list name "
                        "find i me my the a an in on of for by with and movies films movie film please hey hi "
                        "hello can could would will any all some".split())


def role_of(message: str) -> Optional[str]:
    """Role named in the question, or None when it names none."""
    for rx, role in _ROLE_CUES:
        if rx.search(message):
            return role
    return None


def _roles_in(text: str) -> List[Tuple[int, str]]:
    """(position, role) of every role cue in text, in order."""
    out = []
    for rx, role in _ROLE_CUES:
        for m in rx.finditer(text):
            out.append((m.start(), role))
    out.sort()
    return out


def genre_of(message: str) -> Optional[Tuple[str, Tuple[str, ...]]]:
    """(genre word, label stems) of the first genre the question names, or None."""
    for rx, word, stems in GENRES:
        if rx.search(message):
            return word, stems
    return None


def years_of(message: str) -> Optional[Tuple[Optional[int], Optional[int], str]]:
    """(first year, last year, phrase) of the year range the question names, or None."""
    return year_span(message)


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def mask_names(message: str, names) -> str:
    """The question with the given names blanked out (lower case, accents folded), so a genre or year
    word inside a name ("Walt Disney Animation Studios", "Blade Runner 2049") is no filter."""
    text = _fold(message)
    for name in names:
        words = re.findall(r"\w+", _fold(name or ""))
        if words:
            text = re.sub(r"\b" + r"\W+".join(map(re.escape, words)) + r"\b", " ", text)
    return text


def _in_name_run(message: str, tok: str) -> bool:
    """tok sits next to another capitalized word that is not a question word ("Samuel L. Jackson")."""
    if message.isupper():   # shouting: capitals say nothing
        return False
    words = re.findall(r"[\w'’.-]+", message)
    # Title Case typing capitalizes every word: then only non-question words count
    title_case = sum(w[:1].isupper() for w in words) > len(words) / 2
    for i, w in enumerate(words):
        if normalize(w) != tok:
            continue
        for j in (i - 1, i + 1):
            if 0 <= j < len(words):
                n = words[j]
                if not n[:1].isupper() or n == "I":
                    continue
                # a question word capitalized inside a sentence is a first name ("did Will Smith star")
                if normalize(n) not in _LEAD_WORDS or (j > 0 and not title_case):
                    return True
    return False


def _year_phrase(lo: Optional[int], hi: Optional[int]) -> str:
    if lo is not None and hi is not None:
        return f"from {lo}" if lo == hi else f"from {lo} to {hi}"
    return f"since {lo}" if lo is not None else f"until {hi}"


@dataclass
class Overview:
    text: str
    entity_uri: Optional[str]   # None for a missing-name answer
    kind: str
    relation: Optional[str] = None
    property_uri: Optional[str] = None
    inverse: bool = False
    answer_uris: List[str] = field(default_factory=list)
    sparql: Optional[str] = None
    # filters applied to a filmography: {"genre": str, "years": [lo, hi], "count": bool}
    filters: Dict = field(default_factory=dict)


class Filmography:
    def __init__(self, graph, linker):
        self.g = graph
        self.L = linker
        self._genre_cache: Dict = {}

    # ---- linking ----
    def _covers_question(self, cand, message: str) -> bool:
        """Every token of the label occurs in the question (span) or the label is a close typo match."""
        if cand.match == "fuzzy":
            return True
        q = set(normalize(message).split())
        toks = normalize(cand.label).split()
        return bool(toks) and all(t in q for t in toks)

    def _inside_longer(self, cand, qtoks: List[str]) -> bool:
        """The label's words sit inside a longer character, series or film label of the question."""
        lt = cand if isinstance(cand, list) else normalize(cand.label).split()
        n = len(lt)
        if not n:
            return False
        for i in range(len(qtoks) - n + 1):
            if qtoks[i:i + n] != lt:
                continue
            for a in range(max(0, i - 3), i + 1):
                for b in range(i + n, min(len(qtoks), i + n + 3) + 1):
                    if b - a <= n:
                        continue
                    for u in self.L.index.get(" ".join(qtoks[a:b]), ())[:20]:
                        if self.L.kind_of(u) in _CONTAINER_KINDS:
                            return True
        return False

    def _has_credits(self, cand) -> bool:
        ent = rdflib.URIRef(cand.uri)
        return any(True for _, pid in ROLES for _ in self.g.subjects(rdflib.URIRef(WDT + pid), ent))

    def _rest(self, message: str) -> str:
        rest = message
        for rx, _, _ in GENRES:
            rest = rx.sub(" ", rest)
        rest = _NOISE.sub(" ", rest)
        rest = re.sub(r"['’]s\b", " ", rest)
        rest = re.sub(r"[^\w\s&.-]", " ", rest)
        rest = re.sub(r"(?<!\w)[.-]+|[.-]+(?!\w)", " ", rest)
        return re.sub(r"\s+", " ", rest).strip()

    def _surname(self, message: str, kinds) -> list:
        """A person named by surname alone ("Kubrick", "spielberg"): the best-known one with that surname."""
        if "person" not in kinds:
            return []
        out = []
        qtoks = normalize(message).split()
        for tok in dict.fromkeys(normalize(self._rest(message)).split()):
            if len(tok) < 4 or tok in STOP or tok.isdigit():
                continue
            capital = re.search(rf"\b{re.escape(tok[0].upper() + tok[1:])}", message) is not None
            if (len(self.L.tok.get(tok, ())) > SURNAME_MAX_LABELS and not capital) or self._inside_longer([tok], qtoks):
                continue
            # part of a longer capitalized name that did not link ("Samuel L. Jackson"): not a surname
            if _in_name_run(message, tok):
                continue
            uris = self.L.surname.get(tok, ()) or self._surname_typo(tok)
            if not uris:
                continue
            cands = sorted((self.L._cand(u, "span", 1.0, {"person"}, None) for u in uris[:3000]),
                           key=lambda c: -c.degree)
            best = next((c for c in cands[:5] if len(self._all_films(c.uri)) >= SURNAME_MIN_FILMS), None)
            if best is None:
                continue
            # a better-known film, character or series called by the same word wins ("Heat", "Alien")
            other = [u for u in self.L.index.get(tok, ()) if self.L.kind_of(u) != "person"]
            if any(self.L._info(u)[2] >= best.degree for u in other):
                continue
            out.append(best)
        return out

    def _surname_typo(self, tok: str) -> list:
        """Persons whose surname is one edit away from a word no label uses ("hitchcok" -> Hitchcock)."""
        if len(tok) < SURNAME_TYPO_MIN or tok in self.L.tok:
            return []
        letters = "abcdefghijklmnopqrstuvwxyz"
        splits = [(tok[:i], tok[i:]) for i in range(len(tok) + 1)]
        variants = {a + b[1:] for a, b in splits if b}
        variants |= {a + b[1] + b[0] + b[2:] for a, b in splits if len(b) > 1}
        variants |= {a + c + b[1:] for a, b in splits if b for c in letters}
        variants |= {a + c + b for a, b in splits for c in letters}
        uris = []
        for v in sorted(variants):
            uris.extend(self.L.surname.get(v, ()))
        return uris

    def _scan_names(self, message: str, kinds) -> list:
        """Every person/company span of the question; names found are masked and the rest rescanned,
        so a shorter second name is not hidden by a longer first one."""
        qtoks = normalize(message).split()
        text, found = message, []
        for _ in range(3):
            level = [c for c in self.L.scan(text, want=set(kinds), limit=8)
                     if c.kind in kinds and self._covers_question(c, text)
                     and (c.kind != "person" or len(normalize(c.label).split()) >= 2)
                     and not self._inside_longer(c, qtoks) and self._has_credits(c)]
            if not level:
                break
            found.extend(level)
            low = normalize(text)
            for c in level:
                low = re.sub(rf"\b{re.escape(normalize(c.label))}\b", " | ", low)
            text = low
        return found

    def entities(self, message: str, kinds=("person", "company"), surname: bool = True) -> list:
        """Named entities of the wanted kinds in the question, best first, at most one per name."""
        qtoks = normalize(message).split()
        found = self._scan_names(message, kinds)
        if not found:
            rest = self._rest(message)
            if rest and len(rest) >= 4:
                cands = [c for c in self.L.link(rest, want=set(kinds), limit=5) if c.kind in kinds]
                # the whole name (exact or a close typo), not one word of it
                cands = [c for c in cands
                         if (c.match in ("exact", "fuzzy") or self._covers_question(c, rest) and
                             self._coverage(normalize(rest), c.label) >= 0.99)
                         and (c.kind != "person" or len(normalize(c.label).split()) >= 2 or c.match == "fuzzy")
                         and not self._inside_longer(c, qtoks) and self._has_credits(c)]
                found = cands[:1]
        if not found and surname:
            found = self._surname(message, kinds)
        out, seen = [], set()
        for c in found:
            key = normalize(c.label)
            if key not in seen:
                seen.add(key)
                out.append(c)
        # drop a name whose words sit inside another found name's words
        spans = [set(normalize(c.label).split()) for c in out]
        out = [c for i, c in enumerate(out) if not any(i != j and spans[i] < spans[j] for j in range(len(out)))]
        return out

    @staticmethod
    def _coverage(key: str, label: str) -> float:
        toks = [t for t in key.split() if t not in STOP]
        if not toks:
            return 0.0
        lt = set(normalize(label).split())
        return sum(t in lt for t in toks) / len(toks)

    def characters(self, message: str) -> list:
        """Characters and series named in the question, the one with the most films first."""
        rest = normalize(self._rest(message))
        found = [c for c in self.L.scan(message, want={"character", "series"}, limit=10)
                 if c.kind in ("character", "series") and self._covers_question(c, message)
                 and self._coverage(rest, c.label) >= 0.6]   # the whole name, not "Tom" of "Tom Hanx"
        if not found:
            return []
        # keep the longest names only ("Captain Jack Sparrow" over "Jack")
        longest = max(len(normalize(c.label).split()) for c in found)
        found = [c for c in found if len(normalize(c.label).split()) == longest]
        ranked = sorted(found, key=lambda c: (-len(self._labeled_films(self.L.films_of_entity(c.uri))), -c.degree))
        return [c for c in ranked if self._labeled_films(self.L.films_of_entity(c.uri))]

    def _subset_character(self, message: str) -> list:
        """'Jack Sparrow' -> 'Captain Jack Sparrow': a character or series whose label holds the rest."""
        rest = self._rest(message)
        if len(rest.split()) < 2:
            return []
        key = normalize(rest)
        cands = [c for c in self.L.link(rest, want={"character", "series"}, limit=5)
                 if c.kind in ("character", "series") and self._coverage(key, c.label) >= 0.99]
        return [c for c in cands if self._labeled_films(self.L.films_of_entity(c.uri))]

    # ---- graph ----
    def films_by_role(self, uri: str) -> Dict[str, list]:
        """role -> films (URIRef) linked to the entity through that role, best-known first."""
        ent = rdflib.URIRef(uri)
        out = {}
        for role, pid in ROLES:
            films = [s for s in self.g.subjects(rdflib.URIRef(WDT + pid), ent)
                     if isinstance(s, rdflib.URIRef) and self.L.lbl.get(s) and self.L.kind_of(s) == "film"]
            if films:
                films = list(dict.fromkeys(films))
                films.sort(key=lambda f: (-self._depth(f), self.L.lbl.get(f, "")))
                out[role] = films
        return out

    def _all_films(self, uri: str) -> set:
        films = set()
        for fs in self.films_by_role(uri).values():
            films.update(fs)
        return films

    def _labeled_films(self, uris) -> list:
        return [rdflib.URIRef(u) for u in uris if self.L.lbl.get(rdflib.URIRef(u))]

    def description(self, uri) -> Optional[str]:
        for o in self.g.objects(rdflib.URIRef(str(uri)), DESCRIPTION):
            text = str(o).strip()
            if text:
                return text
        return None

    def _depth(self, uri) -> int:
        return self.L._info(uri)[2]

    def _genre_labels(self, film) -> List[str]:
        hit = self._genre_cache.get(film)
        if hit is None:
            hit = [normalize(self.L.lbl.get(o, "")) for p in (P136, P31) for o in self.g.objects(film, p)]
            hit = [h for h in hit if h]
            self._genre_cache[film] = hit
        return hit

    def _filter(self, films, genre, years) -> list:
        out = []
        for f in films:
            if genre and not any(stem in lab for lab in self._genre_labels(f) for stem in genre[1]):
                continue
            if years:
                lo, hi = years[0], years[1]
                y = self.L._year(f)
                if y is None or (lo is not None and y < lo) or (hi is not None and y > hi):
                    continue
            out.append(f)
        return out

    def _names(self, films, n=MAX_LISTED) -> str:
        labels = [self.L.lbl[f] for f in films[:n]]
        more = len(films) - len(labels)
        text = ", ".join(labels[:-1]) + (f" and {labels[-1]}" if len(labels) > 1 else labels[0])
        return text + (f", and {more} more" if more > 0 else "")

    @staticmethod
    def _sparql(pid: str, qid: str) -> str:
        return (
            "PREFIX wd: <http://www.wikidata.org/entity/>\n"
            "PREFIX wdt: <http://www.wikidata.org/prop/direct/>\n"
            f"SELECT DISTINCT ?movie WHERE {{\n  ?movie wdt:{pid} wd:{qid} .\n  ?movie wdt:P31 wd:Q11424 .\n}}"
        )

    # ---- answers ----
    def answer(self, message: str, film_overview: bool = True, report_missing: bool = False,
               role: Optional[str] = None, genre: Optional[str] = None,
               years: Optional[Tuple[Optional[int], Optional[int]]] = None,
               count: Optional[bool] = None, roles: Optional[Dict[str, str]] = None) -> Optional[Overview]:
        """
        Filmography of the person/company named in the question, the films of a named character or
        series, or an overview of a named film. role/genre/years/count override what the wording
        gives (callers that parsed the question already). roles: name as typed -> role, for the
        people of a shared-films question. report_missing: when nothing links, say that the graph
        has no entity of the capitalized name the question uses.
        """
        people = self.entities(message, surname=False)
        chars = [] if people else (self.characters(message) or self._subset_character(message))
        # genre and year words inside a linked name are part of the name, not a filter
        masked = mask_names(message, [c.label for c in people + chars])
        if genre is None:
            g = genre_of(masked)
        else:
            g = next(((w, s) for rx, w, s in GENRES if w == genre or rx.search(genre)), (genre, (normalize(genre),)))
        if years is None:
            y = years_of(masked)
        else:
            y = (years[0], years[1], years[2] if len(years) > 2 else _year_phrase(years[0], years[1]))
        want_count = bool(_COUNT.search(message)) if count is None else count
        if not people:
            if film_overview and _ABOUT.search(message):
                film = self._film_named(message)
                # the longer name wins: "Star Wars" (series) over "Star!" (film), "Heat" film over nothing
                if film and not (chars and len(normalize(chars[0].label).split()) > len(normalize(film.label).split())):
                    return self._film(film)
            if chars:
                return self._character(chars[0], message, g, y, want_count)
            # a person named by surname alone, once no character or series holds the word
            people = self._surname(message, ("person",))
        if people:
            if len(people) >= 2:
                shared = self._shared(people[:3], message, role, roles)
                if shared:
                    return shared
            r = role or role_of(message)
            return self._person(self._namesake_with_role(people[0], r), r, g, y, want_count)
        if report_missing:
            return self.missing(message)
        return None

    def _namesake_with_role(self, cand, role: Optional[str]):
        """Among people of the same name, the best-known one credited in the role asked ("John Williams" + music)."""
        if not role or cand.kind == "company" or role in self.films_by_role(cand.uri):
            return cand
        for alt in self.L.alternatives(cand, limit=10):
            if role in self.films_by_role(alt.uri):
                return alt
        return cand

    def _film_named(self, message):
        films = [c for c in self.L.scan(message, want={"film"}, limit=5)
                 if c.kind == "film" and self._covers_question(c, message)]
        return films[0] if films else None

    def _person(self, cand, role: Optional[str], genre=None, years=None, count=False) -> Optional[Overview]:
        credits = self.films_by_role(cand.uri)
        if not credits:
            return None
        if cand.kind == "company" and role in COMPANY_ROLE:
            role = COMPANY_ROLE[role]
        name = cand.label
        filters = {}
        if genre:
            filters["genre"] = genre[0]
        if years:
            filters["years"] = [years[0], years[1]]
        if count:
            filters["count"] = True
        if genre or years:
            credits = {r: self._filter(fs, genre, years) for r, fs in credits.items()}
        kind_word = f"{genre[0]} film" if genre else "film"
        when = f" {years[2]}" if years else ""
        if role and role in credits and (credits[role] or genre or years):
            films = credits[role]
            verb = {
                "cast member": f"{name} appears in", "director": f"{name} directed",
                "screenwriter": f"{name} wrote", "composer": f"{name} scored",
                "producer": f"{name} produced", "production company": f"{name} produced",
                "cinematographer": f"{name} shot", "distributed by": f"{name} distributed",
            }[role]
            if not films:
                text = f"The graph lists no {kind_word}{when} with {name} as {role}."
                return Overview(text, cand.uri, cand.kind, role, WDT + ROLE_PROP[role], True, [],
                                self._sparql(ROLE_PROP[role], cand.qid), filters)
            text = (f"{verb} {len(films)} {kind_word}{'s' if len(films) != 1 else ''}{when} in the graph: "
                    f"{self._names(films)}.")
            return Overview(text, cand.uri, cand.kind, role, WDT + ROLE_PROP[role], True,
                            [str(f) for f in films], self._sparql(ROLE_PROP[role], cand.qid), filters)
        # no role named, or none matching: the whole filmography, largest role first
        credits = {r: fs for r, fs in credits.items() if fs}
        if not credits:
            text = f"The graph lists no {kind_word}{when} for {name}."
            return Overview(text, cand.uri, cand.kind, None, None, True, [], None, filters)
        order = sorted(credits, key=lambda r: -len(credits[r]))
        lead = order[0]
        lines = []
        for r in order:
            films = credits[r]
            lines.append(f"{r} of {len(films)} {kind_word}{'s' if len(films) != 1 else ''} "
                         f"({self._names(films, 5 if r != lead else MAX_LISTED)})")
        prefix = ""
        if role and role not in credits:
            prefix = f"The graph lists no {kind_word}{when} with {name} as {role}. "
        uris = []
        for r in order:
            uris.extend(str(f) for f in credits[r] if str(f) not in uris)
        desc = self.description(cand.uri)
        who = f"{name} ({desc})" if desc else name
        if count or genre or years:
            head = f"{who} has {len(uris)} {kind_word}{'s' if len(uris) != 1 else ''}{when} in the graph: "
        else:
            head = f"{who} in the graph: "
        text = prefix + head + "; ".join(lines) + "."
        return Overview(text, cand.uri, cand.kind, lead, WDT + ROLE_PROP[lead], True, uris,
                        self._sparql(ROLE_PROP[lead], cand.qid), filters)

    def _person_roles(self, people, message: str, role: Optional[str]) -> List[Optional[str]]:
        """Role of each person: the cue just before the name, else the first cue after it."""
        if role:
            return [role] * len(people)
        low = normalize(message)
        spots = []
        for p in people:
            key = normalize(p.label)
            i = low.find(key)
            spots.append((i if i >= 0 else len(low), i + len(key) if i >= 0 else len(low)))
        order = sorted(range(len(people)), key=lambda k: spots[k][0])
        roles = [None] * len(people)
        for n, k in enumerate(order):
            start, end = spots[k]
            prev_end = spots[order[n - 1]][1] if n else 0
            next_start = spots[order[n + 1]][0] if n + 1 < len(order) else len(low)
            before = _roles_in(low[prev_end:start])
            after = _roles_in(low[end:next_start])
            if before:
                roles[k] = before[-1][1]
            elif after:
                roles[k] = after[0][1]
        if all(r is None for r in roles):
            shared = role_of(message)
            if shared:
                return [shared] * len(people)
        return roles

    @staticmethod
    def _roles_by_name(people, roles: List[Optional[str]], given: Dict[str, str]) -> List[Optional[str]]:
        """Roles the parser read per name ("made with Y": Y as cast) override the cue-position guess."""
        out = list(roles)
        for i, p in enumerate(people):
            lt = set(normalize(p.label).split())
            best, hits = None, 0
            for name, r in given.items():
                n = sum(t in lt for t in normalize(name).split())
                if n > hits:
                    best, hits = r, n
            if best:
                out[i] = best
        return out

    def _shared(self, people, message: str, role: Optional[str] = None,
                given: Optional[Dict[str, str]] = None) -> Optional[Overview]:
        roles = self._person_roles(people, message, role)
        if given:
            roles = self._roles_by_name(people, roles, given)
        # no role named for anyone ("What did X and Y do together?"): films where both have any credit
        any_role = all(r is None for r in roles)
        sets = []
        for i, (p, r) in enumerate(zip(people, roles)):
            if p.kind == "company" and r in COMPANY_ROLE:
                r = COMPANY_ROLE[r]
            p = people[i] = self._namesake_with_role(p, r)
            credits = self.films_by_role(p.uri)
            if any_role:
                films = list(dict.fromkeys(f for fs in credits.values() for f in fs))
                lead = max(credits, key=lambda x: len(credits[x])) if credits else "cast member"
                sets.append((lead, films))
                continue
            if r is None:
                # no role named for this person: their largest role
                r = max(credits, key=lambda x: len(credits[x])) if credits else "cast member"
            sets.append((r, credits.get(r, [])))
        roles = [r for r, _ in sets]
        common = [f for f in sets[0][1] if all(f in s for _, s in sets[1:])]
        if any_role:
            common.sort(key=lambda f: (-self._depth(f), self.L.lbl.get(f, "")))
        names = " and ".join(p.label for p in people) if len(people) == 2 else \
            ", ".join(p.label for p in people[:-1]) + f" and {people[-1].label}"
        lead_role = roles[0]
        pid = ROLE_PROP[lead_role]
        same = len(set(roles)) == 1
        if any_role:
            n = f"{len(common)} film{'s' if len(common) != 1 else ''}"
            text = (f"{names} worked together on {n} in the graph: {self._names(common)}." if common
                    else f"The graph has no film that credits both {names}.")
            return Overview(text, people[0].uri, people[0].kind, lead_role, WDT + pid, True,
                            [str(f) for f in common], self._sparql(pid, people[0].qid))
        if not common:
            if same:
                text = f"The graph has no film with both {names} as {lead_role}."
            else:
                text = "The graph has no film with " + " and ".join(
                    f"{p.label} as {r}" for p, r in zip(people, roles)) + "."
            return Overview(text, people[0].uri, people[0].kind, lead_role, WDT + pid, True, [],
                            self._sparql(pid, people[0].qid))
        n = f"{len(common)} film{'s' if len(common) != 1 else ''}"
        if same and lead_role == "cast member":
            text = f"{names} are both in {n}: {self._names(common)}."
        elif same:
            text = f"Films with {names} as {lead_role}: {self._names(common)}."
        else:
            text = "The graph has " + n + " with " + " and ".join(
                f"{p.label} as {r}" for p, r in zip(people, roles)) + f": {self._names(common)}."
        return Overview(text, people[0].uri, people[0].kind, lead_role, WDT + pid, True, [str(f) for f in common],
                        self._sparql(pid, people[0].qid))

    def performers(self, uri) -> list:
        """Named actors linked to a character as its performer (P175), best-known first."""
        out = [o for o in dict.fromkeys(self.g.objects(rdflib.URIRef(str(uri)), P175))
               if isinstance(o, rdflib.URIRef) and self.L.lbl.get(o)]
        return sorted(out, key=lambda a: (-self._depth(a), self.L.lbl[a]))

    def _character(self, cand, message: str, genre=None, years=None, count=False,
                   who: bool = False) -> Optional[Overview]:
        """Films of a character or series, or the cast behind a character ('Who played Gandalf?').
        who: the caller knows the question asks who plays the character."""
        if role_of(message) not in (None, "cast member"):
            return None   # "who composed the music for <character>": a fact read through its films (responser)
        films = self._labeled_films(self.L.films_of_entity(cand.uri))
        if genre or years:
            films = self._filter(films, genre, years)
        asks_who = cand.kind == "character" and (who or _WHO_PLAYED.search(message))
        if asks_who:
            actors = self.performers(cand.uri)
            if actors:
                names = [self.L.lbl[a] for a in actors[:MAX_CAST]]
                listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"
                text = f"{cand.label} is played by {listed} (performer links of the character in the graph)."
                if films:
                    text += f" {cand.label} appears in {len(films)} film{'s' if len(films) != 1 else ''}: " \
                            f"{self._names(films, 4)}."
                return Overview(text, cand.uri, cand.kind, "cast member", WDT + "P175", False,
                                [str(a) for a in actors[:MAX_CAST]], None, {"performers": True})
        if not films:
            return None
        what = "series" if cand.kind == "series" else "character"
        n = f"{len(films)} film{'s' if len(films) != 1 else ''}"
        if asks_who:
            cast = Counter()
            for f in films:
                for o in set(self.g.objects(f, P161)):
                    if self.L.lbl.get(o):
                        cast[o] += 1
            if cast:
                ranked = sorted(cast, key=lambda a: (-cast[a], -self._depth(a), self.L.lbl[a]))[:MAX_CAST]
                parts = [f"{self.L.lbl[a]} ({cast[a]} film{'s' if cast[a] != 1 else ''})" for a in ranked]
                text = (f"The graph does not say who plays {cand.label} directly; {cand.label} appears in {n} "
                        f"({self._names(films, 4)}). Their most frequent cast members: {', '.join(parts)}.")
                return Overview(text, cand.uri, cand.kind, "cast member", WDT + "P161", False,
                                [str(a) for a in ranked], None, {"via_films": True})
        if count:
            text = f"The graph links {n} to the {what} {cand.label}: {self._names(films)}."
        else:
            text = f"{cand.label} ({what}) appears in {n} in the graph: {self._names(films)}."
        filters = {"count": True} if count else {}
        return Overview(text, cand.uri, cand.kind, None, None, False, [str(f) for f in films], None, filters)

    def missing(self, message: str, names=()) -> Optional[Overview]:
        """'The graph has no entity named X' for a capitalized name of two to four words, or one of the
        given names (the parser's mention, any case), that links to nothing."""
        words = re.findall(r"[\w'’.-]+", message)
        runs, cur = [], []
        for w in words + [""]:
            if w and w[0].isupper() and w.lower().strip(".") not in _LEAD_WORDS:
                cur.append(w)
                continue
            if 2 <= len(cur) <= 4:
                runs.append(" ".join(cur))
            cur = []
        runs += [n for n in names if n and 2 <= len(n.split()) <= 4 and n not in runs]
        for name in runs:
            name = re.sub(r"['’]s$", "", name)
            key = normalize(name)
            hits = [c for c in self.L.link(name, limit=5)
                    if c.match in ("exact", "fuzzy") or self._coverage(key, c.label) >= 0.99]
            if not hits:
                return Overview(f"The graph has no entity named {name}, so I cannot answer this from the graph.",
                                None, "missing", None, None, False, [], None, {"missing": name})
        return None

    def _film(self, cand) -> Optional[Overview]:
        f = rdflib.URIRef(cand.uri)

        def names(pid, n=4):
            vals = [self.L.lbl.get(o) for o in self.g.objects(f, rdflib.URIRef(WDT + pid))]
            return [v for v in vals if v][:n]

        directors, cast, genres = names("P57", 3), names("P161", 4), names("P136", 3)
        bits = [f"{cand.label}{f' ({cand.year})' if cand.year else ''} is a film"]
        if directors:
            bits.append(f"directed by {' and '.join(directors)}")
        text = " ".join(bits) + "."
        desc = self.description(cand.uri)
        if desc and not directors:
            text = f"{cand.label}{f' ({cand.year})' if cand.year else ''}: {desc}."
        if genres:
            text += f" Genre: {', '.join(genres)}."
        if cast:
            text += f" Starring {', '.join(cast[:-1]) + ' and ' + cast[-1] if len(cast) > 1 else cast[0]}."
        return Overview(text, cand.uri, "film", None, None, False, [cand.uri], None)
