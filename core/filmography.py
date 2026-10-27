# filmography.py
# Fallback answers for questions that name a person, company or film but whose wording the
# intent parser does not cover: "In which movies Daniel Radcliffe played?", "Daniel Radcliffe
# films", "Tom Hanks filmography", "Who is Daniel Radcliffe?", "Tell me about Inception",
# "Which movies did Emma Watson and Daniel Radcliffe play in together?".
# Pure graph lookups through the entity linker; no embeddings, no guessing.

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import rdflib

from core.linker import normalize

WDT = "http://www.wikidata.org/prop/direct/"
DESCRIPTION = rdflib.URIRef("http://schema.org/description")

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
# words removed before linking the remainder of the question as a name
_NOISE = re.compile(
    r"\b(?:in|on|of|for|by|with|which|what|who|whom|whose|where|when|how|did|does|do|has|have|had|is|are|was|were|been|be|"
    r"the|a|an|all|any|some|list|show|me|tell|give|name|please|movies?|films?|filmography|works?|career|credits?|roles?|"
    r"play(?:s|ed|ing)?|act(?:s|ed|ing)?|starr?(?:s|ed|ing)?|appear(?:s|ed|ing)?|featur(?:e|es|ed|ing)|direct(?:s|ed|ing)?|"
    r"made|make|wr[io]te|written|compos(?:e|ed)|scor(?:e|ed)|produc(?:e|ed)|shot|together|both|and|about|info|known|"
    r"famous|popular|best|other|else|also|ever|so\s+far|until\s+now)\b", re.I)

MAX_LISTED = 6


def role_of(message: str) -> Optional[str]:
    """Role named in the question, or None when it names none."""
    for rx, role in _ROLE_CUES:
        if rx.search(message):
            return role
    return None


@dataclass
class Overview:
    text: str
    entity_uri: str
    kind: str
    relation: Optional[str] = None
    property_uri: Optional[str] = None
    inverse: bool = False
    answer_uris: List[str] = field(default_factory=list)
    sparql: Optional[str] = None


class Filmography:
    def __init__(self, graph, linker):
        self.g = graph
        self.L = linker

    # ---- linking ----
    def _covers_question(self, cand, message: str) -> bool:
        """Every token of the label occurs in the question (span) or the label is a close typo match."""
        if cand.match == "fuzzy":
            return True
        q = set(normalize(message).split())
        toks = normalize(cand.label).split()
        return bool(toks) and all(t in q for t in toks)

    def entities(self, message: str, kinds=("person", "company")) -> list:
        """Named entities of the wanted kinds in the question, best first, at most one per name."""
        found = [c for c in self.L.scan(message, want=set(kinds), limit=8)
                 if c.kind in kinds and self._covers_question(c, message)]
        # a person named by two or more words, or a company
        found = [c for c in found if c.kind != "person" or len(normalize(c.label).split()) >= 2]
        if not found:
            rest = _NOISE.sub(" ", message)
            rest = re.sub(r"['’]s\b", " ", rest)
            rest = re.sub(r"[^\w\s&.-]", " ", rest)
            rest = re.sub(r"\s+", " ", rest).strip()
            if rest and len(rest) >= 4:
                found = [c for c in self.L.link(rest, want=set(kinds), limit=5) if c.kind in kinds]
                if found and found[0].match == "fuzzy" and found[0].score < 0:
                    found = []
        out, seen = [], set()
        for c in found:
            key = normalize(c.label)
            if key not in seen:
                seen.add(key)
                out.append(c)
        return out

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

    def description(self, uri) -> Optional[str]:
        for o in self.g.objects(rdflib.URIRef(str(uri)), DESCRIPTION):
            text = str(o).strip()
            if text:
                return text
        return None

    def _depth(self, uri) -> int:
        return self.L._info(uri)[2]

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
    def answer(self, message: str, film_overview: bool = True) -> Optional[Overview]:
        """Filmography of the person/company named in the question, or an overview of a named film."""
        people = self.entities(message)
        if people:
            role = role_of(message)
            if len(people) >= 2 and (_TOGETHER.search(message) or re.search(r"\band\b", message, re.I)):
                shared = self._shared(people[:3], role or "cast member")
                if shared:
                    return shared
            return self._person(people[0], role)
        if film_overview and _ABOUT.search(message):
            films = [c for c in self.L.scan(message, want={"film"}, limit=5)
                     if c.kind == "film" and self._covers_question(c, message)]
            if films:
                return self._film(films[0])
        return None

    def _person(self, cand, role: Optional[str]) -> Optional[Overview]:
        credits = self.films_by_role(cand.uri)
        if not credits:
            return None
        name = cand.label
        if role and role in credits:
            films = credits[role]
            verb = {
                "cast member": f"{name} appears in", "director": f"{name} directed",
                "screenwriter": f"{name} wrote", "composer": f"{name} scored",
                "producer": f"{name} produced", "production company": f"{name} produced",
                "cinematographer": f"{name} shot", "distributed by": f"{name} distributed",
            }[role]
            text = f"{verb} {len(films)} film{'s' if len(films) != 1 else ''} in the graph: {self._names(films)}."
            return Overview(text, cand.uri, cand.kind, role, WDT + ROLE_PROP[role], True,
                            [str(f) for f in films], self._sparql(ROLE_PROP[role], cand.qid))
        # no role named, or none matching: the whole filmography, largest role first
        order = sorted(credits, key=lambda r: -len(credits[r]))
        lead = order[0]
        lines = []
        for r in order:
            films = credits[r]
            label = "cast member" if r == "cast member" else r
            lines.append(f"{label} of {len(films)} film{'s' if len(films) != 1 else ''} "
                         f"({self._names(films, 5 if r != lead else MAX_LISTED)})")
        prefix = ""
        if role and role not in credits:
            prefix = f"The graph lists no film with {name} as {role}. "
        desc = self.description(cand.uri)
        who = f"{name} ({desc})" if desc else name
        text = prefix + f"{who} in the graph: " + "; ".join(lines) + "."
        uris = []
        for r in order:
            uris.extend(str(f) for f in credits[r] if str(f) not in uris)
        return Overview(text, cand.uri, cand.kind, lead, WDT + ROLE_PROP[lead], True, uris,
                        self._sparql(ROLE_PROP[lead], cand.qid))

    def _shared(self, people, role: str) -> Optional[Overview]:
        pid = ROLE_PROP[role]
        sets = []
        for p in people:
            films = self.films_by_role(p.uri).get(role, [])
            sets.append(films)
        common = [f for f in sets[0] if all(f in s for s in sets[1:])]
        names = " and ".join(p.label for p in people) if len(people) == 2 else \
            ", ".join(p.label for p in people[:-1]) + f" and {people[-1].label}"
        if not common:
            text = f"The graph has no film with both {names} as {role}."
            return Overview(text, people[0].uri, people[0].kind, role, WDT + pid, True, [], self._sparql(pid, people[0].qid))
        text = f"{names} are both in {len(common)} film{'s' if len(common) != 1 else ''}: {self._names(common)}." \
            if role == "cast member" else \
            f"Films with {names} as {role}: {self._names(common)}."
        return Overview(text, people[0].uri, people[0].kind, role, WDT + pid, True, [str(f) for f in common],
                        self._sparql(pid, people[0].qid))

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
