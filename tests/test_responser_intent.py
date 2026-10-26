#!/usr/bin/env python3
"""
Checks for the intent + linker route of core/responser.py on a small synthetic graph.

No dataset needed (ratings and image caches are stubbed); runs in seconds.

    env -u PYTHONPATH .venv/bin/python -B tests/test_responser_intent.py
"""

import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402
from rdflib import Graph, Literal, URIRef  # noqa: E402
from rdflib.namespace import RDFS  # noqa: E402

import core.data as data  # noqa: E402

data._ratings_cache = {}  # keep data/ratings out of the test

import core.responser as responser  # noqa: E402
from core.intent import Intent  # noqa: E402
from core.responser import Responser  # noqa: E402

responser._IMAGE_MAP.update({"poster": {}, "profile": {}})  # keep data/additional out of the test

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


# films
ent("F1", "Good Will Hunting", "Q11424", "1997-12-05")
ent("F2", "Heat", "Q11424", "1995-12-15")
ent("F3", "Heat", "Q11424", "1986-03-14")
ent("F4", "Inception", "Q11424", "2010-07-16")
ent("F5", "Interstellar", "Q11424", "2014-11-07")
ent("F6", "Pirates One", "Q11424", "2003-07-09")
ent("F7", "Pirates Two", "Q11424", "2006-07-07")
ent("F8", "Hero Film", "Q11424", "2001-01-01")
ent("F9", "Mystery Movie", "Q11424", "1999-01-01")
# people
ent("H1", "Christopher Nolan", "Q5")
ent("H2", "Gus Van Sant", "Q5")
ent("H3", "Matt Damon", "Q5")
ent("H4", "Robin Williams", "Q5")
ent("H5", "Michael Mann", "Q5")
ent("H6", "Al Pacino", "Q5")
ent("H7", "Robert De Niro", "Q5")
ent("H8", "Dick Richards", "Q5")
ent("H9", "Hans Zimmer", "Q5")
ent("H10", "Klaus Badelt", "Q5")
ent("H11", "Danny Elfman", "Q5")
# character, series, genre
ent("C1", "Captain Jack Sparrow", "Q15773347")
ent("C2", "Lonely Hero", "Q15773347")
ent("S1", "Dark Saga", "Q24856")
ent("C3", "The Director", "Q15773347")  # a character whose name is a relation word
ent("F10", "Space Toys", "Q11424", "1995-11-22")  # a film and a series with one name
ent("S2", "Space Toys", "Q24856")
ent("F11", "Space Toys 2", "Q11424", "1999-11-24")
link("F10", "P57", "H2")
link("F10", "P86", "H11")
link("F10", "P161", "H3")
link("F11", "P57", "H5")
link("F10", "P179", "S2")
link("F11", "P179", "S2")
g.add((e("Q157443"), RDFS.label, Literal("comedy film", lang="en")))

link("F1", "P57", "H2")
link("F1", "P161", "H3")
link("F1", "P161", "H4")
link("F1", "P86", "H11")
link("F2", "P57", "H5")
link("F2", "P161", "H6")
link("F2", "P161", "H7")
link("F3", "P57", "H8")
link("F4", "P57", "H1")
link("F4", "P86", "H9")
link("F4", "P136", "Q157443")
link("F4", "P179", "S1")
link("F5", "P57", "H1")
link("F5", "P86", "H9")
link("F5", "P179", "S1")
link("F6", "P674", "C1")
link("F6", "P86", "H9")
link("F6", "P86", "H10")
link("F7", "P674", "C1")
link("F7", "P86", "H9")
link("F8", "P674", "C2")
link("F9", "P57", "Q999")  # a director without any label
g.add((e("H12"), RDFS.label, Literal("Untagged Writer")))  # label without a language tag, as in data/graph.nt
g.add((e("H12"), p("P31"), e("Q5")))
link("F1", "P58", "H12")

# TransE embeddings: F9 + r(P58) lands on Danny Elfman, F9 + r(P86) on the unnamed Q999
ent_uris = [str(e(q)) for q in ("F9", "Q999", "H11", "F1", "F4", "C2")]
ent_ids = {u: i for i, u in enumerate(ent_uris)}
id_to_ent = {i: u for u, i in ent_ids.items()}
E = np.zeros((len(ent_uris), 4))
E[1] = [10, 0, 0, 0]
E[2] = [0, 10, 0, 0]
E[3] = [0, 0, 10, 0]
E[4] = [0, 0, 0, 10]
E[5] = [-10, 0, 0, 0]
rel_uris = [P + "P58", P + "P86", P + "P57"]
rel_ids = {u: i for i, u in enumerate(rel_uris)}
R = np.array([[0, 10, 0, 0], [10, 0, 0, 0], [0, 0, 10, 0]], dtype=float)

plain = Responser()
embed = Responser(E, R, ent_ids, rel_ids, id_to_ent)

passed = failed = 0
META_KEYS = {"intent", "subject_kind", "via_films", "alternatives", "parts", "route", "entity_uri",
             "relation", "answer_uris"}


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS {name}")
    else:
        failed += 1
        print(f"FAIL {name} {detail}")


def ask(r, q):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ans = r.generate_response(q, g)
    meta = r.last_meta
    check(f"meta keys [{q}]", META_KEYS <= set(meta), sorted(META_KEYS - set(meta)))
    return ans, meta


# --- film subject through the intent path ---
a, m = ask(plain, "Who directed Good Will Hunting?")
check("film: answer", "Gus Van Sant" in a, a)
check("film: route factual", m["route"] == "factual", m["route"])
check("film: entity", m["entity_uri"] == str(e("F1")), m["entity_uri"])
check("film: subject_kind", m["subject_kind"] == "film", m["subject_kind"])
check("film: intent dict", isinstance(m["intent"], dict) and m["intent"]["relation"] == "director", m["intent"])
check("film: no via_films, no alternatives", m["via_films"] == [] and m["alternatives"] == [])
check("film: one part", len(m["parts"]) == 1 and m["parts"][0]["relation"] == "director", m["parts"])
check("film: answer_uris", m["answer_uris"] == [str(e("H2"))], m["answer_uris"])

a, m = ask(plain, "Who wrote the screenplay of Good Will Hunting?")
check("film: untagged label value", "Untagged Writer" in a and m["intent"] is not None, (a, m["intent"]))

a, m = ask(plain, "Who scored Inception?")
check("paraphrase: composer", "Hans Zimmer" in a and m["relation"] == "composer", (a, m["relation"]))

a, m = ask(plain, "who directed good will hunthing")
check("typo: linked film", m["entity_uri"] == str(e("F1")) and "Gus Van Sant" in a, (a, m["entity_uri"]))
a, m = ask(plain, "director of good will hunthing")
check("typo not hidden by a question span", m["entity_uri"] == str(e("F1")) and "Gus Van Sant" in a,
      (a, m["entity_uri"]))

# --- ambiguous title ---
a, m = ask(plain, "Who directed Heat?")
check("ambiguous: popular film wins", "Michael Mann" in a, a)
check("ambiguous: sentence", "(There are 2 entries called Heat; this is the 1995 film.)" in a, a)
check("ambiguous: alternatives meta",
      [(x["qid"], x["year"], x["kind"]) for x in m["alternatives"]] == [("F3", 1986, "film")], m["alternatives"])
check("ambiguous: alternative keys", set(m["alternatives"][0]) == {"uri", "qid", "label", "year", "kind"}
      if m["alternatives"] else False)
a, m = ask(plain, "Who directed Heat (1986)?")
check("year hint: 1986 film", "Dick Richards" in a and m["entity_uri"] == str(e("F3")), (a, m["entity_uri"]))

# --- character and series through their films ---
a, m = ask(plain, "Who composed the music for Jack Sparrow?")
check("character: text", a.startswith("Captain Jack Sparrow is not a film itself; the graph links it to 2 films. "
                                      "The composer of those films: Hans Zimmer (2 films), Klaus Badelt (1 film)."), a)
check("character: subject_kind", m["subject_kind"] == "character", m["subject_kind"])
check("character: via_films", m["via_films"] == [str(e("F6")), str(e("F7"))], m["via_films"])
check("character: entity is the character", m["entity_uri"] == str(e("C1")), m["entity_uri"])
check("character: route factual", m["route"] == "factual", m["route"])
check("character: answer_uris", set(m["answer_uris"]) == {str(e("H9")), str(e("H10"))}, m["answer_uris"])

a, m = ask(plain, "Who directed Space Toys?")
check("singular title: the film", m["entity_uri"] == str(e("F10")) and "Gus Van Sant" in a, (a, m["entity_uri"]))
check("singular title: series named as alternative", "S2" in [x["qid"] for x in m["alternatives"]], m["alternatives"])
a, m = ask(plain, "Who directed the Space Toys movies?")
check("plural form: the series", m["entity_uri"] == str(e("S2")) and "Michael Mann (1 film)" in a, (a, m["entity_uri"]))

a, m = ask(plain, "Who directed the Heat movies?")
check("plural form: no series named Heat, film kept", "Michael Mann" in a, a)

a, m = ask(plain, "Who directed Dark Saga?")
check("series: text", "Dark Saga is not a film itself; the graph links it to 2 films." in a
      and "Christopher Nolan (2 films)" in a, a)
check("series: subject_kind", m["subject_kind"] == "series", m["subject_kind"])

a, m = ask(plain, "Who directed Dark Saga's movies?")
check("films_of form on a series: via films", "Christopher Nolan (2 films)" in a and m["subject_kind"] == "series",
      (a, m["subject_kind"]))

a, m = ask(embed, "Who composed the music for Lonely Hero?")
check("character without values: no prediction", m["route"] == "factual" and "Note:" not in a, (m["route"], a))
check("character without values: says so", "Lonely Hero is not a film itself" in a, a)
check("character without values: via_films", m["via_films"] == [str(e("F8"))], m["via_films"])

# 1.4 singular form and "and N more"
one = Responser._via_text("X", "director", 1, [("u", "A", 1), (None, "B", 1)])
check("1.4 singular", one == "X is not a film itself; the graph links it to 1 film. The director of that film: A, B.", one)
many = Responser._via_text("X", "composer", 9, [(None, f"V{i}", 9 - i) for i in range(8)])
check("1.4 at most 6 values and 'more'", many.endswith("V5 (4 films), and 2 more.") and "V6" not in many, many)

# --- films_of ---
a, m = ask(plain, "Which movies did Christopher Nolan direct?")
check("films_of: both films", "Inception" in a and "Interstellar" in a, a)
check("films_of: inverse meta", m["inverse"] is True and m["entity_uri"] == str(e("H1"))
      and m["subject_kind"] == "person", (m["inverse"], m["entity_uri"], m["subject_kind"]))
a, m = ask(plain, "Which comedy movies did Nolan direct?")
check("films_of: genre filter + surname", "Inception" in a and "Interstellar" not in a, a)
a, m = ask(plain, "Movies with Matt Damon")
check("films_of: cast", "Good Will Hunting" in a and m["relation"] == "cast member", (a, m["relation"]))

# --- sub-questions ---
a, m = ask(plain, "Who directed Good Will Hunting and who starred in it?")
check("parts: both answers in order", a.find("Gus Van Sant") < a.find("Matt Damon") and "Gus Van Sant" in a
      and "Matt Damon" in a, a)
check("parts: two entries", [x["relation"] for x in m["parts"]] == ["director", "cast member"], m["parts"])
check("parts: entry keys", all(set(x) == {"relation", "entity_uri", "answer_uris", "answer"} for x in m["parts"]))
check("parts: top relation is the first", m["relation"] == "director", m["relation"])
a, m = ask(plain, "Who directed Inception and when was it released?")
check("parts: date", "Christopher Nolan" in a and "2010" in a, a)

# --- fallbacks ---
real_parse = responser.parse_intent
responser.parse_intent = lambda q: Intent(kind="unknown", relation=None, mention=None)
try:
    a, m = ask(plain, "Who directed Good Will Hunting?")
finally:
    responser.parse_intent = real_parse
check("old path answers when intent fails", "Gus Van Sant" in a, a)
check("old path: intent None", m["intent"] is None and m["parts"] == [], m["intent"])
check("old path: subject_kind filled", m["subject_kind"] == "film", m["subject_kind"])

a, m = ask(plain, "Who directed Blorptastic Quest Nine?")
check("unlinked: no intent answer", m["intent"] is None, (a, m["intent"]))

a, m = ask(embed, "Who wrote Mystery Movie?")
check("TransE: head from linker", m["route"] == "prediction" and m["entity_uri"] == str(e("F9")), (m["route"], m["entity_uri"]))
check("TransE: named prediction", "Danny Elfman" in a and "prediction" in a, a)
check("TransE: subject_kind", m["subject_kind"] == "film", m["subject_kind"])
check("TransE: intent dict", isinstance(m["intent"], dict), m["intent"])

a, m = ask(embed, "Who composed the music for Mystery Movie?")
check("TransE: unnamed prediction refused", a == "No answer: the prediction has no name in the graph.", a)
check("TransE: no answer uris", m["answer_uris"] == [], m["answer_uris"])
check("TransE: no bare QID", "Q999" not in a, a)

# --- other routes unchanged ---
a, m = ask(plain, "Show me a picture of Matt Damon")
check("multimedia route", m["route"] == "multimedia" and m["intent"] is None, (m["route"], m["intent"]))
try:
    a, m = ask(plain, "Recommend movies similar to Inception")
    check("recommendation route", m["route"] == "recommendation" and m["intent"] is None, (m["route"], m["intent"]))
except Exception as exc:  # the recommender may need data files; the route is what matters here
    check("recommendation route", plain.last_meta.get("route") == "recommendation", repr(exc))

total = passed + failed
print(f"\n{passed}/{total} passed")
sys.exit(1 if failed else 0)
