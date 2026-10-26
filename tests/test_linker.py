#!/usr/bin/env python3
"""
Checks for the entity linker (core/linker.py) on a small synthetic graph.

No dataset needed; runs in seconds.

    env -u PYTHONPATH .venv/bin/python -B tests/test_linker.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rdflib import Graph, Literal, URIRef  # noqa: E402

from core.linker import EntityLinker, get_linker, normalize  # noqa: E402

WD = "http://www.wikidata.org/entity/"
P = "http://www.wikidata.org/prop/direct/"
P31, P577, P57, P674, P179, P161 = (URIRef(P + x) for x in ("P31", "P577", "P57", "P674", "P179", "P161"))


def e(q):
    return URIRef(WD + q)


g = Graph()
labels = {}


def ent(q, label, cls, date=None):
    labels[e(q)] = label
    g.add((e(q), P31, e(cls)))
    if date:
        g.add((e(q), P577, Literal(date)))


def link(a, rel, b):
    g.add((e(a), URIRef(P + rel), e(b)))


ent("F1", "Titanic", "Q11424", "1997-12-19")
ent("F2", "Titanic", "Q11424", "1953-04-11")
ent("F3", "Gladiator", "Q11424", "2000-05-01")
ent("F4", "The Lord of the Rings: The Fellowship of the Ring", "Q11424", "2001-12-19")
ent("F5", "Tom & Jerry", "Q11424", "1992-01-01")
ent("F6", "Amélie", "Q11424", "2001-04-25")
ent("F7", "Pirates of the Caribbean: The Curse of the Black Pearl", "Q11424", "2003-07-09")
ent("F8", "Pirates of the Caribbean: Dead Man's Chest", "Q202866", "2006-07-07")
ent("F9", "Batman Begins", "Q11424", "2005-06-15")
ent("F10", "The Dark Knight", "Q11424", "2008-07-18")
ent("F11", "Interstellar", "Q11424", "2014-11-05")
ent("F12", "Titanic", "Q7725634")  # a literary work with the same name
ent("P1", "Christopher Nolan", "Q5")
ent("P2", "Charles Noland", "Q5")
ent("P3", "Leonardo DiCaprio", "Q5")
ent("C1", "Captain Jack Sparrow", "Q15773347")
ent("S1", "Batman", "Q24856")
ent("S2", "Pirates of the Caribbean", "Q196600")
ent("S3", "Batman", "Q196600")  # a second entity with the same name and kind
ent("K1", "Warner Bros.", "Q1762059")

for f in ("F9", "F10", "F11"):
    link(f, "P57", "P1")
for i in range(8):
    labels[e("X%d" % i)] = "Extra %d" % i
    link("F9", "P161", "X%d" % i)
    link("F1", "P161", "X%d" % i)
link("F1", "P57", "P3")
link("F2", "P57", "P2")
link("F7", "P674", "C1")
link("F8", "P674", "C1")
link("F7", "P179", "S2")
link("F8", "P179", "S2")
link("F9", "P179", "S1")
link("F10", "P179", "S1")
link("F10", "P179", "S3")
link("F9", "P31", "S1")

labels = {k: v for k, v in labels.items()}
t0 = time.time()
lk = EntityLinker(g, labels)

results = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    results.append(bool(cond))


def top(*a, **kw):
    r = lk.link(*a, **kw)
    return r[0] if r else None


c = top("Gladiator", want={"film"})
check("exact match", c and c.qid == "F3" and c.match == "exact" and c.kind == "film")

c = top("lord of the rings: the fellowship of the ring", want={"film"})
check("article dropped on both sides", c and c.qid == "F4" and c.match == "exact")

c = top("the gladiator", want={"film"})
check("article added in the mention", c and c.qid == "F3")

c = top("Amelie", want={"film"})
check("accents folded", c and c.qid == "F6")

c = top("Tom and Jerry", want={"film"})
check("ampersand equals 'and'", c and c.qid == "F5")
check("normalize keeps digits and drops punctuation", normalize("It’s “Mr. 3000”!") == "its mr 3000")

c = top("the movie Interstellar", want={"film"})
check("span inside a longer mention", c and c.qid == "F11" and c.match == "span")

c = top("who directed", want={"film"}, question="Who directed Interstellar?")
check("span found in the question", c and c.qid == "F11")

c = top("Gladiater", want={"film"})
check("typo links by fuzzy match", c and c.qid == "F3" and c.match == "fuzzy")

c = top("Titanic", want={"film"})
check("popularity tie-break: 1997 beats 1953", c and c.qid == "F1")
c = top("Titanic", want={"film"}, year=1953)
check("year hint wins outright", c and c.qid == "F2")
c = top("Titanic", want={"film"}, year=1997)
check("year hint 1997", c and c.qid == "F1")
c = top("Titanic", want={"film", "character"})
check("want filter ranks films over the literary work", c and c.kind == "film")

c = top("Nolan", want={"person"})
check("surname-only person: highest degree, not Noland", c and c.qid == "P1")
c = top("Christopher Nolan", want={"person"})
check("full name exact", c and c.qid == "P1" and c.match == "exact")

c = top("Jack Sparrow", want={"film", "character", "series"})
check("character by token subset", c and c.qid == "C1" and c.kind == "character")
check("character -> films", lk.films_of_entity(e("C1")) == [WD + "F7", WD + "F8"])

c = top("Pirates of the Caribbean", want={"film", "character", "series"})
check("series kind (media franchise)", c and c.qid == "S2" and c.kind == "series")
check("series -> films sorted by year", lk.films_of_entity(e("S2")) == [WD + "F7", WD + "F8"])
check("film class animated film is a film", lk.kind_of(e("F8")) == "film")

c = top("Batman movies", want={"series", "film"})
check("plural film word stripped", c and c.label == "Batman" and c.kind == "series")
check("batman series -> films", lk.films_of_entity(e("S1")) == [WD + "F9", WD + "F10"])

best = top("Batman", want={"series"})
alts = lk.alternatives(best)
check("alternatives: same name and kind, other entity", len(alts) == 1 and alts[0].qid != best.qid and alts[0].label == "Batman")
t_alts = lk.alternatives(top("Titanic", want={"film"}))
check("alternatives skip other kinds", [a.qid for a in t_alts] == ["F2"])

cs = lk.link("Titanic", want={"person"})
check("want filter: no person called Titanic still returns ranked others", all(c.kind != "person" for c in cs))
c = top("Warner Bros", want={"company"})
check("company kind", c and c.qid == "K1" and c.kind == "company")

scan = lk.scan("Who directed The Dark Knight and Batman Begins?", want={"film"})
check("scan finds the longest film spans", {c.qid for c in scan} >= {"F9", "F10"})
check("kind_of person", lk.kind_of(e("P1")) == "person")
check("kind_of unknown", lk.kind_of(e("X1")) == "other")
check("empty mention", lk.link("") == [])

check("get_linker caches per graph", get_linker(g, labels) is get_linker(g, labels))
check("runs in seconds", time.time() - t0 < 10)

print("%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
