#!/usr/bin/env python3
"""
Checks for ordinal questions about a series ("Who composed the first Harry Potter film?"):
the intent parser (ordinal value, stripped mention, titles that start with an ordinal word) and the
responser on a small synthetic graph (series members, character crossovers, title families,
"there is no tenth one", multi-part questions).

    env -u PYTHONPATH .venv/bin/python -B tests/test_ordinal.py
"""

import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rdflib import Graph, Literal, URIRef  # noqa: E402
from rdflib.namespace import RDFS  # noqa: E402

import core.data as data  # noqa: E402

data._ratings_cache = {}  # keep data/ratings out of the test

import core.responser as responser  # noqa: E402
from core.intent import parse_intent  # noqa: E402
from core.responser import Responser  # noqa: E402

responser._IMAGE_MAP.update({"poster": {}, "profile": {}})  # keep data/additional out of the test

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS {name}")
    else:
        failed += 1
        print(f"FAIL {name} {detail}")


# --- intent parser -------------------------------------------------------------------------------

PARSE = [
    ("Who composed first film of the Harry Potter?", "composer", "Harry Potter", 1),
    ("Who composed the first Harry Potter film?", "composer", "Harry Potter", 1),
    ("Who directed the last Harry Potter movie?", "director", "Harry Potter", -1),
    ("When was the second Harry Potter movie released?", "publication date", "Harry Potter", 2),
    ("Who directed the third film in the Harry Potter series?", "director", "Harry Potter series", 3),
    ("Who directed Harry Potter's first film?", "director", "Harry Potter", 1),
    ("Who is the director of the 2nd Hunger Games movie?", "director", "Hunger Games", 2),
    ("Who directed the most recent James Bond film?", "director", "James Bond", -1),
    ("Who directed the final Lord of the Rings film?", "director", "Lord of the Rings", -1),
    ("Who directed the original Jurassic Park?", "director", "Jurassic Park", 1),
    ("Who wrote the screenplay of the first Twilight film?", "screenwriter", "Twilight", 1),
    ("When was the first Shrek released?", "publication date", "Shrek", 1),
    ("Who directed the very first Star Wars movie?", "director", "Star Wars", 1),
]
for q, rel, mention, ordinal in PARSE:
    it = parse_intent(q)
    check(f"parse: {q}", (it.kind, it.relation, it.mention, it.ordinal) == ("fact", rel, mention, ordinal),
          (it.kind, it.relation, it.mention, it.ordinal))

# a capitalised ordinal word is part of a title
for q, mention in [("Who directed The Last Samurai?", "The Last Samurai"), ("Who directed First Blood?", "First Blood"),
                   ("Who starred in The Final Destination?", "The Final Destination")]:
    it = parse_intent(q)
    check(f"title kept: {q}", it.mention == mention and it.ordinal is None, (it.mention, it.ordinal))
# lower-case title: the ordinal is kept, but the raw mention lets the responser find the film
it = parse_intent("who directed the last samurai")
check("lower-case title: raw mention kept", it.ordinal == -1 and it.raw_mention and "last samurai" in it.raw_mention.lower(),
      (it.ordinal, it.raw_mention))
# words after the ordinal that make it something else
it = parse_intent("When did the first time travel film come out?")
check("not an ordinal: 'the first time'", it.ordinal is None, it.ordinal)
# "and" questions share the ordinal
it = parse_intent("Who directed and wrote the first Matrix film?")
check("parts share the ordinal", it.ordinal == 1 and it.parts and it.parts[0].ordinal == 1 and it.parts[0].mention == "Matrix",
      (it.ordinal, [(p.mention, p.ordinal) for p in it.parts]))
check("to_dict has ordinal", parse_intent("Who directed the first Shrek?").to_dict()["ordinal"] == 1)

# --- responser on a small graph ------------------------------------------------------------------

WD = "http://www.wikidata.org/entity/"
P = "http://www.wikidata.org/prop/direct/"


def e(q):
    return URIRef(WD + q)


def p(x):
    return URIRef(P + x)


g = Graph()


def ent(q, label, cls, date=None):
    g.add((e(q), RDFS.label, Literal(label, lang="en")))
    g.add((e(q), p("P31"), e(cls)))
    if date:
        g.add((e(q), p("P577"), Literal(date)))


def link(a, rel, b):
    g.add((e(a), p(rel), e(b)))


# a wizard series (members out of order in the graph), a character that also appears in a crossover
ent("S1", "Wizard Boy", "Q24856")
ent("C1", "Wizard Boy", "Q15773347")
ent("W2", "Wizard Boy and the Second Book", "Q11424", "2002-11-03")
ent("W1", "Wizard Boy and the First Stone", "Q11424", "2001-11-04")
ent("W3", "Wizard Boy and the Third Prison", "Q11424", "2004-05-31")
ent("X1", "Space Ball: A New Legacy", "Q11424", "2021-07-16")
for f in ("W1", "W2", "W3"):
    link(f, "P179", "S1")
    link(f, "P674", "C1")
link("X1", "P674", "C1")
ent("H1", "John Composer", "Q5")
ent("H2", "Chris Director", "Q5")
ent("H3", "Alfonso Director", "Q5")
ent("H4", "Nick Composer", "Q5")
link("W1", "P86", "H1")
link("W1", "P57", "H2")
link("W2", "P57", "H2")
link("W3", "P57", "H3")
link("W3", "P86", "H4")
# a title family with no series entity
ent("T1", "Robot Pals", "Q11424", "1995-11-22")
ent("T2", "Robot Pals 2", "Q11424", "1999-11-24")
ent("T3", "Robot Pals 3", "Q11424", "2010-06-18")
ent("T4", "Robot Pals of Terror", "Q11424", "2013-10-16")  # a special, not a numbered sequel
ent("H5", "Pete Director", "Q5")
ent("H6", "Lee Director", "Q5")
link("T1", "P57", "H5")
link("T3", "P57", "H6")
# a series whose name has a series word ("The Night Saga") and is asked as "Night"
ent("S2", "The Night Saga", "Q24856")
ent("N1", "Night", "Q11424", "2008-11-21")
ent("N2", "The Night Saga: New Moon", "Q11424", "2009-11-20")
link("N1", "P179", "S2")
link("N2", "P179", "S2")
ent("H7", "Catherine Director", "Q5")
ent("H8", "Chris Weitz", "Q5")
link("N1", "P57", "H7")
link("N2", "P57", "H8")
# a film whose title starts with an ordinal word
ent("L1", "The Last Swordsman", "Q11424", "2003-12-05")
ent("L2", "Swordsman", "Q11424", "1990-01-01")
ent("L3", "Swordsman II", "Q11424", "1992-01-01")
ent("H9", "Edward Director", "Q5")
link("L1", "P57", "H9")

r = Responser()


def ask(q):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ans = r.generate_response(q, g)
    return ans, r.last_meta


a, m = ask("Who composed the first Wizard Boy film?")
check("series: first film named", "The first of the 3 Wizard Boy films in the graph is Wizard Boy and the First Stone (2001)." in a, a)
check("series: its composer", "John Composer" in a and "Nick Composer" not in a, a)
check("series: entity is the film", m["entity_uri"] == str(e("W1")), m["entity_uri"])
check("series: family in release order", m.get("family") == [str(e(q)) for q in ("W1", "W2", "W3")], m.get("family"))
check("series: not a via-films answer", m["via_films"] == [], m["via_films"])

a, m = ask("Who directed the last Wizard Boy movie?")
check("series: last", "Wizard Boy and the Third Prison (2004)" in a and "Alfonso Director" in a, a)
a, m = ask("Who directed the second film in the Wizard Boy series?")
check("series: 'second film in the X series'", "Wizard Boy and the Second Book (2002)" in a and "Chris Director" in a, a)
a, m = ask("Who directed Wizard Boy's third film?")
check("series: possessive", "Alfonso Director" in a, a)
a, m = ask("Who directed the tenth Wizard Boy film?")
check("series: beyond the end", a.startswith("The graph has only 3 Wizard Boy films, so there is no tenth one"), a)
a, m = ask("Who composed the second Wizard Boy film?")
check("series: no value for that film", "The graph has no composer for it." in a, a)
a, m = ask("Who directed and composed the first Wizard Boy film?")
check("parts: lead said once", a.count("The first of the 3 Wizard Boy films") == 1 and "Chris Director" in a
      and "John Composer" in a, a)

a, m = ask("Who directed the first Robot Pals film?")
check("title family: first", "Robot Pals (1995)" in a and "Pete Director" in a, a)
a, m = ask("Who directed the latest Robot Pals movie?")
check("title family: specials left out", "Robot Pals 3 (2010)" in a and "Lee Director" in a, a)
check("title family: count", "of the 3 Robot Pals films" in a, a)

a, m = ask("Who directed the second Night film?")
check("series by name words: 'Night' -> 'The Night Saga'", "The Night Saga: New Moon (2009)" in a and "Chris Weitz" in a, a)

a, m = ask("who directed the last swordsman")
check("lower-case title with an ordinal word: the film", "Edward Director" in a and "of the" not in a, a)

a, m = ask("Who directed Wizard Boy and the First Stone?")
check("plain title still works", "Chris Director" in a and "films in the graph" not in a, a)

# --- ordinal spans outside fact questions ---------------------------------------------------------
from core.intent import ordinal_span  # noqa: E402

for q, phrase, series, value in [
    ("Show me the poster of the first Harry Potter film", "the first Harry Potter film", "Harry Potter", 1),
    ("Recommend movies like the third film in the Toy Story series, please", "the third film in the Toy Story series",
     "Toy Story", 3),
    ("Show a picture from the last Matrix movie", "the last Matrix movie", "Matrix", -1),
    ("What is the first Harry Potter movie?", "the first Harry Potter movie", "Harry Potter", 1),
]:
    s = ordinal_span(q)
    check(f"span: {q}", s is not None and q[s[0]:s[1]] == phrase and s[2:] == (series, value), s)
check("span: titles are not ordinals", ordinal_span("Show me the poster of The Last Samurai") is None)

a, m = ask("What is the first Wizard Boy movie?")
check("identity: names the film", a == "The first of the 3 Wizard Boy films in the graph is Wizard Boy and the First Stone (2001).", a)
check("identity: meta", m["entity_uri"] == str(e("W1")) and m["route"] == "factual" and len(m["family"]) == 3, m)
a, m = ask("Which film is the last Robot Pals?")
check("identity: title family", "Robot Pals 3 (2010)" in a, a)
a, m = ask("Recommend movies like the first Wizard Boy film")
check("other routes: question rewritten with the title", m.get("rewritten") == 'Recommend movies like "Wizard Boy and the First Stone"',
      m.get("rewritten"))

total = passed + failed
print(f"\n{passed}/{total} passed")
sys.exit(1 if failed else 0)
