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

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
