#!/usr/bin/env python3
"""
Checks for the filmography fallback (core/filmography.py) on a small synthetic graph.

No dataset needed; runs in seconds.

    env -u PYTHONPATH .venv/bin/python -B tests/test_filmography.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rdflib import Graph, Literal, URIRef  # noqa: E402

from core.filmography import Filmography, role_of  # noqa: E402
from core.linker import EntityLinker  # noqa: E402

WD = "http://www.wikidata.org/entity/"
P = "http://www.wikidata.org/prop/direct/"
DESC = URIRef("http://schema.org/description")

g = Graph()
labels = {}


def e(q):
    return URIRef(WD + q)


def ent(q, label, cls, date=None, desc=None):
    labels[e(q)] = label
    g.add((e(q), URIRef(P + "P31"), e(cls)))
    if date:
        g.add((e(q), URIRef(P + "P577"), Literal(date)))
    if desc:
        g.add((e(q), DESC, Literal(desc)))


def link(a, prop, b):
    g.add((e(a), URIRef(P + prop), e(b)))


ent("F1", "Harry Potter and the Philosopher's Stone", "Q11424", "2001-11-04")
ent("F2", "Harry Potter and the Chamber of Secrets", "Q11424", "2002-11-03")
ent("F3", "The Woman in Black", "Q11424", "2012-02-03")
ent("F4", "Inception", "Q11424", "2010-07-08")
ent("F5", "The Bling Ring", "Q11424", "2013-06-14")
ent("P1", "Daniel Radcliffe", "Q5", desc="British actor and film producer (born 1989)")
ent("P2", "Emma Watson", "Q5")
ent("P3", "Christopher Nolan", "Q5")
ent("P4", "Chris Columbus", "Q5")
ent("G1", "science fiction film", "Q201658")
for f in ("F1", "F2", "F3"):
    link(f, "P161", "P1")
for f in ("F1", "F2", "F5"):
    link(f, "P161", "P2")
for f in ("F1", "F2"):
    link(f, "P57", "P4")
link("F4", "P57", "P3")
link("F4", "P136", "G1")
for s, label in labels.items():
    g.add((s, URIRef("http://www.w3.org/2000/01/rdf-schema#label"), Literal(label)))

F = Filmography(g, EntityLinker(g, labels))


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + detail))
    return cond


results = []

# role words
for q, want in [
    ("In which movies Daniel Radcliffe played?", "cast member"),
    ("What movies has Daniel Radcliffe been in?", "cast member"),
    ("Films starring Daniel Radcliffe", "cast member"),
    ("What movies did Christopher Nolan make?", "director"),
    ("Which films has Hans Zimmer scored?", "composer"),
    ("Daniel Radcliffe movies", None),
    ("Tom Hanks filmography", None),
    ("Who is Daniel Radcliffe?", None),
    ("Movies that actually matter to Tom Hanks", None),
]:
    got = role_of(q)
    results.append(check(f"role of {q!r}", got == want, f"want {want}, got {got}"))

# filmographies in every wording
for q in [
    "In which movies Daniel Radcliffe played?",
    "What movies has Daniel Radcliffe been in?",
    "Daniel Radcliffe movies",
    "daniel radcliffe films",
    "Show me Daniel Radcliffe's filmography",
    "Daniel Radcliffe played in which movies?",
    "Where did Daniel Radcliffe act?",
    "Who is Daniel Radcliffe?",
]:
    ov = F.answer(q)
    ok = ov is not None and ov.entity_uri == str(e("P1")) and len(ov.answer_uris) == 3 and "Daniel Radcliffe" in ov.text
    results.append(check(f"filmography: {q!r}", ok, f"got {ov}"))

ov = F.answer("In which movies Daniel Radcliffe played?")
results.append(check("cast role: relation, inverse, P161 and SPARQL",
                     ov is not None and ov.relation == "cast member" and ov.inverse
                     and (ov.property_uri or "").endswith("P161") and "P161" in (ov.sparql or "")))
ov = F.answer("Who is Daniel Radcliffe?")
results.append(check("overview carries the graph description", ov is not None and "British actor" in ov.text))

ov = F.answer("Which movies did Emma Watson and Daniel Radcliffe play in together?")
results.append(check("films shared by two people",
                     ov is not None and sorted(ov.answer_uris) == sorted([str(e("F1")), str(e("F2"))]) and "both" in ov.text,
                     f"got {ov}"))

ov = F.answer("What movies did Christopher Nolan make?")
results.append(check("director role", ov is not None and ov.relation == "director" and ov.answer_uris == [str(e("F4"))]))

ov = F.answer("Which films did Daniel Radcliffe direct?")
results.append(check("missing role falls back to the whole filmography with a note",
                     ov is not None and "no film with Daniel Radcliffe as director" in ov.text and len(ov.answer_uris) == 3,
                     f"got {ov}"))

ov = F.answer("Tell me about Inception")
results.append(check("film overview", ov is not None and ov.kind == "film" and "Christopher Nolan" in ov.text, f"got {ov}"))
results.append(check("no film overview when the caller turns it off", F.answer("Tell me about Inception", film_overview=False) is None))

for q in ["What is the capital of France?", "Hello", "Who directed it?"]:
    results.append(check(f"nothing for {q!r}", F.answer(q) is None))

# ---- question-robustness group 4: surnames, filters, counts, characters, namesakes, gaps ----
from core.filmography import genre_of, years_of  # noqa: E402

g2 = Graph()
labels2 = {}


def ent2(q, label, cls=None, date=None, desc=None):
    labels2[e(q)] = label
    if cls:
        g2.add((e(q), URIRef(P + "P31"), e(cls)))
    if date:
        g2.add((e(q), URIRef(P + "P577"), Literal(date)))
    if desc:
        g2.add((e(q), DESC, Literal(desc)))


def link2(a, prop, b):
    g2.add((e(a), URIRef(P + prop), e(b)))


ent2("GC", "comedy film", "Q201658")
ent2("GD", "drama film", "Q201658")
ent2("GW", "Western film", "Q201658")
# a director known by surname, eight films from 1958 to 1972
films = [("W1", "Dust Road", "1958", "GW"), ("W2", "Paper Moonrise", "1961", "GC"), ("W3", "Lantern Bay", "1963", "GD"),
         ("W4", "The Tin Parade", "1964", "GC"), ("W5", "Ashfield", "1966", "GD"), ("W6", "Copper Sky", "1968", "GW"),
         ("W7", "North Gate", "1970", "GD"), ("W8", "Little Hours", "1972", "GC")]
for q, label, year, genre in films:
    ent2(q, label, "Q11424", f"{year}-05-01")
    link2(q, "P57", "D1")
    link2(q, "P136", genre)
ent2("D1", "Orson Wellesby", "Q5", desc="director (born 1920)")
ent2("D2", "Mabel Wellesby", "Q5")          # a namesake with one credit
link2("W3", "P161", "D2")
# an actor in five of them and a studio whose class has no label
ent2("A1", "Nora Vale", "Q5")
for q in ("W2", "W4", "W5", "W6", "W8"):
    link2(q, "P161", "A1")
ent2("K1", "Moonbeam Works", "Q999001", desc="animation studio")
for q in ("W2", "W4", "W8"):
    link2(q, "P272", "K1")
# a character and a series used by films; a person inside the character's name
ent2("C1", "Captain Nora Vale", "Q15773347")
for q in ("W5", "W6", "W7"):
    link2(q, "P674", "C1")
ent2("S1", "Copper Saga", "Q24856")
for q in ("W6", "W7", "W8"):
    link2(q, "P179", "S1")
# namesakes: an actor and a composer called Jonah Reed
ent2("J1", "Jonah Reed", "Q5", desc="actor")
ent2("J2", "Jonah Reed", "Q5", desc="composer")
for q in ("W1", "W2", "W3"):
    link2(q, "P161", "J1")
for q in ("W5", "W7"):
    link2(q, "P86", "J2")
# a common word that is also a surname
ent2("B1", "Pete Golden", "Q5")
for q, *_ in films[:5]:
    link2(q, "P161", "B1")
for i in range(45):
    ent2(f"GL{i}", f"Golden Hour {i}")
for s, label in labels2.items():
    g2.add((s, URIRef("http://www.w3.org/2000/01/rdf-schema#label"), Literal(label)))
F2 = Filmography(g2, EntityLinker(g2, labels2))
W = lambda *qs: sorted(str(e(q)) for q in qs)  # noqa: E731


def ans(q, **kw):
    return F2.answer(q, **kw)


# year and genre parsing
for q, want in [
    ("films from the sixties", (1960, 1969)), ("in the 1960s", (1960, 1969)), ("from the 60's", (1960, 1969)),
    ("late 60s", (1967, 1969)), ("early 2000s", (2000, 2003)), ("after 1965", (1966, None)), ("since 1965", (1965, None)),
    ("before 1963", (None, 1962)), ("between 1961 and 1964", (1961, 1964)), ("from 1961 to 1964", (1961, 1964)),
    ("released in 1964", (1964, 1964)), ("Who is Orson Wellesby?", None), ("2001: A Space Odyssey", None),
]:
    got = years_of(q)
    results.append(check(f"years of {q!r}", (got[:2] if got else None) == want, f"got {got}"))
for q, want in [("his comedies", "comedy"), ("a rom-com", "romantic comedy"), ("any sci-fi?", "science fiction"),
                ("westerns", "western"), ("Copper Saga films", None), ("star wars movies", None)]:
    got = genre_of(q)
    results.append(check(f"genre of {q!r}", (got[0] if got else None) == want, f"got {got}"))

# surname only, any case
ov = ans("What did Wellesby direct?")
results.append(check("surname only -> best-known person", ov is not None and ov.entity_uri == str(e("D1"))
                     and len(ov.answer_uris) == 8, f"got {ov}"))
ov = ans("how many films did wellesby direct")
results.append(check("lower-case surname count names the number", ov is not None and "8 films" in ov.text
                     and ov.filters.get("count"), f"got {ov}"))
# filters
ov = ans("Wellesby films from the sixties")
results.append(check("decade filter", ov is not None and sorted(ov.answer_uris) == W("W2", "W3", "W4", "W5", "W6")
                     and "1960s" in ov.text, f"got {ov}"))
ov = ans("Wellesby movies after 1965")
results.append(check("after-year filter", ov is not None and sorted(ov.answer_uris) == W("W5", "W6", "W7", "W8"), f"got {ov}"))
ov = ans("Orson Wellesby films before 1962")
results.append(check("before-year filter", ov is not None and sorted(ov.answer_uris) == W("W1", "W2"), f"got {ov}"))
ov = ans("Orson Wellesby comedies")
results.append(check("genre filter", ov is not None and sorted(ov.answer_uris) == W("W2", "W4", "W8")
                     and "comedy" in ov.text, f"got {ov}"))
ov = ans("Which westerns did Orson Wellesby direct in the late 60s?")
results.append(check("genre + years + role", ov is not None and ov.answer_uris == [str(e("W6"))]
                     and ov.relation == "director", f"got {ov}"))
ov = ans("Orson Wellesby musicals")
results.append(check("empty filter says so, lists nothing", ov is not None and not ov.answer_uris
                     and "no musical film" in ov.text, f"got {ov}"))
ov = ans("Orson Wellesby films", years=(1961, 1963), genre="comedy", count=True)
results.append(check("caller overrides for years, genre, count", ov is not None and ov.answer_uris == [str(e("W2"))]
                     and ov.filters == {"genre": "comedy", "years": [1961, 1963], "count": True}, f"got {ov}"))
# typos in names
ov = ans("Orsen Welesby movies")
results.append(check("typo in both words", ov is not None and ov.entity_uri == str(e("D1")), f"got {ov}"))
# company whose class has no label: linked by use, 'made' means production company
ov = ans("What did Moonbeam Works make?")
results.append(check("studio by use, 'make' -> production company", ov is not None and ov.relation == "production company"
                     and sorted(ov.answer_uris) == W("W2", "W4", "W8"), f"got {ov}"))
ov = ans("How many movies did Moonbeam Works produce?")
results.append(check("company count", ov is not None and "3 films" in ov.text, f"got {ov}"))
ov = ans("Who is Moonbeam Works?")
results.append(check("who is <company>", ov is not None and "animation studio" in ov.text, f"got {ov}"))
# characters and series
ov = ans("Who portrayed Captain Nora Vale?")
results.append(check("who played <character> -> cast of its films, not the person in its name",
                     ov is not None and ov.entity_uri == str(e("C1")) and str(e("A1")) in ov.answer_uris
                     and "Nora Vale (2 films)" in ov.text, f"got {ov}"))
ov = ans("Which films is Captain Nora Vale in?")
results.append(check("films of a character", ov is not None and sorted(ov.answer_uris) == W("W5", "W6", "W7"), f"got {ov}"))
ov = ans("How many Copper Saga movies exist?")
results.append(check("series count", ov is not None and "3 films" in ov.text and ov.kind == "series", f"got {ov}"))
ov = ans("Nora Vale films")
results.append(check("the person herself still answers for her own name", ov is not None and ov.entity_uri == str(e("A1"))
                     and len(ov.answer_uris) == 5, f"got {ov}"))
# namesakes chosen by the role asked
ov = ans("Which films did Jonah Reed compose?")
results.append(check("namesake with the asked role (composer)", ov is not None and ov.entity_uri == str(e("J2"))
                     and sorted(ov.answer_uris) == W("W5", "W7"), f"got {ov}"))
ov = ans("Which films did Jonah Reed act in?")
results.append(check("namesake with the asked role (actor)", ov is not None and ov.entity_uri == str(e("J1")), f"got {ov}"))
# shared films with a role per person
ov = ans("Films by Orson Wellesby with music by Jonah Reed")
results.append(check("mixed roles: director + composer namesake", ov is not None and sorted(ov.answer_uris) == W("W5", "W7")
                     and "as composer" in ov.text and "as director" in ov.text, f"got {ov}"))
ov = ans("Orson Wellesby and Nora Vale movies")
results.append(check("no role named: each person's largest role", ov is not None
                     and sorted(ov.answer_uris) == W("W2", "W4", "W5", "W6", "W8"), f"got {ov}"))
ov = ans("Which films did Nora Vale and Pete Golden star in together?")
results.append(check("same role for both", ov is not None and sorted(ov.answer_uris) == W("W2", "W4", "W5")
                     and "both in 3 films" in ov.text, f"got {ov}"))
# guards
results.append(check("common word is not a surname in lower case", F2.entities("golden oldies please") == []))
results.append(check("rec wording without a name finds nobody", F2.entities("good drama films please") == []))
ov = ans("What did Bartholomew Quince direct?", report_missing=True)
results.append(check("unlabeled name: says the graph has no entity named it", ov is not None and not ov.answer_uris
                     and "no entity named Bartholomew Quince" in ov.text, f"got {ov}"))
results.append(check("no gap report unless asked", ans("What did Bartholomew Quince direct?") is None))
ov = ans("Which films did Bartholomew Wellesby direct?", report_missing=True)
results.append(check("full name that does not link does not fall back to its surname",
                     ov is not None and ov.entity_uri != str(e("D1")), f"got {ov}"))
results.append(check("no gap report for a non-name question",
                     ans("What is the capital of France?", report_missing=True) is None))

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
