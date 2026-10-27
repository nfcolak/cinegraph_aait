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
link("F10", "P58", "H11")  # Danny Elfman also wrote a film: a plausible screenwriter guess
# for the year, namesake, count and picture checks
ent("F12", "Ocean Tale", "Q11424", "1953-04-11")
link("F12", "P57", "H5")
ent("H13", "Sam Lee", "Q5")       # an actor ...
ent("H14", "Sam Lee", "Q5")       # ... and a director of the same name
link("F2", "P161", "H13")
link("F1", "P161", "H13")
link("F8", "P57", "H14")
ent("Q166", "Golden Bear", "Q618779")
link("F4", "P166", "Q166")
ent("Q167", "Silver Bear", "Q618779")
link("F4", "P166", "Q167")

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
check("unlinked: the missing name is reported", "graph has no entity named Blorptastic Quest Nine" in a
      and m["gap"] and m["answer_uris"] == [], (a, m["gap"]))
check("unlinked: the relation asked is kept", m["relation"] == "director", m["relation"])

# a linked film without the value: the gap first, the embedding guess only as a note
a, m = ask(embed, "Who wrote Mystery Movie?")
check("TransE: head from linker", m["route"] == "prediction" and m["entity_uri"] == str(e("F9")), (m["route"], m["entity_uri"]))
check("TransE: gap first", a.startswith("The graph has no screenwriter for Mystery Movie (1999)."), a)
check("TransE: named guess as a note", "(Note:" in a and "Danny Elfman" in a and "prediction" in a, a)
check("TransE: guess has no card", m["answer_uris"] == [] and m["gap"], (m["answer_uris"], m["gap"]))
check("TransE: subject_kind", m["subject_kind"] == "film", m["subject_kind"])
check("TransE: intent dict", isinstance(m["intent"], dict), m["intent"])

a, m = ask(embed, "Who composed the music for Mystery Movie?")
check("TransE: unnamed nearest entity skipped", a.startswith("The graph has no composer for Mystery Movie (1999).")
      and "Q999" not in a, a)
check("TransE: guess is a credited composer", "Danny Elfman" in a, a)
check("TransE: no answer uris", m["answer_uris"] == [], m["answer_uris"])

# the guess must be a value of the relation somewhere: Danny Elfman directed nothing
E_dir = Responser(E, R, ent_ids, rel_ids, id_to_ent)
a, m = ask(E_dir, "Who directed Interstellar?")
check("TransE not used when the graph has the value", "Christopher Nolan" in a and m["route"] == "factual", a)
a, m = ask(embed, "Who directed Mystery Movie?")
check("unnamed value: says the graph has no name", "has a director in the graph (Q999)" in a
      and "no name" in a and "Note:" not in a, a)
check("unnamed value: no card, gap", m["answer_uris"] == [] and m["gap"], (m["answer_uris"], m["gap"]))
a, m = ask(plain, "Who is the cinematographer of Inception?")
check("no value, no embeddings: specific gap", a == "The graph has no cinematographer for Inception (2010).", a)
a, m = ask(plain, "What awards did Interstellar win?")
check("no award: award noun", a == "The graph has no award for Interstellar (2014).", a)

# --- year that no film of that name has ---
a, m = ask(plain, "Who directed Ocean Tale (1997)?")
check("year miss: says so", a.startswith("The graph has no film called Ocean Tale from 1997; it has Ocean Tale (1953)"), a)
check("year miss: no value of another year", "Michael Mann" not in a and m["answer_uris"] == [] and m["gap"], a)
a, m = ask(plain, "Who directed the 1953 Ocean Tale?")
check("year hit: answer", "Michael Mann" in a and not m["gap"], a)
a, m = ask(plain, "Who directed Heat (1996)?")
check("year off by one still counts", "Michael Mann" in a, a)

# --- counts on the intent path ---
a, m = ask(plain, "How many awards did Inception win?")
check("fact count: number first", a.startswith("Inception has 2 awards in the graph.") and "Golden Bear" in a, a)

# --- namesakes: the one credited in the role asked ---
a, m = ask(plain, "Which films did Sam Lee direct?")
check("namesake with the role", "Hero Film" in a and m["entity_uri"] == str(e("H14")), (a, m["entity_uri"]))

# --- films of a character, not its cast ---
a, m = ask(plain, "Which movies feature Captain Jack Sparrow?")
check("character films: titles", "Pirates One" in a and "Pirates Two" in a and "Hans Zimmer" not in a, a)
check("character films: cards are the films", set(m["answer_uris"]) == {str(e("F6")), str(e("F7"))}, m["answer_uris"])
check("character films: compact", m.get("compact") is True, m.get("compact"))

# --- year range on the intent path ---
a, m = ask(plain, "Which movies did Christopher Nolan direct after 2012?")
check("year range: filtered", "Interstellar" in a and "Inception" not in a, a)
check("year range: the wording's phrase is kept", "after 2012" in a, a)

# --- old path entity lookup through the linker's index (no label scans) ---
from core.entity import resolve_entity  # noqa: E402
check("resolve: case-insensitive exact", resolve_entity(g, {}, "good WILL hunting") == [e("F1")])
check("resolve: substring of a label", e("C1") in resolve_entity(g, {}, "Jack Sparrow"))
check("resolve: unknown word gives nothing", resolve_entity(g, {}, "Zorbleflax Returns") == [])

# --- other routes unchanged ---
a, m = ask(plain, "Show me a picture of Matt Damon")
check("multimedia route", m["route"] == "multimedia" and m["intent"] is None, (m["route"], m["intent"]))
for q in ("I want to see Matt Damon", "Show me Robin Williams", "Heat poster", "Let me see Gus Van Sant"):
    a, m = ask(plain, q)
    check(f"picture wording [{q}]", m["route"] == "multimedia", (m["route"], a))
for q in ("show me movies with Matt Damon", "Show me some comedies", "Matt Damon movies", "Did you see Inception?",
          "Have you seen Heat?"):
    a, m = ask(plain, q)
    check(f"not a picture [{q}]", m["route"] != "multimedia", (m["route"], a))
a, m = ask(plain, "Show me a picture of Quorble Vantastic")
check("picture of a name the graph lacks", "graph has no entity named Quorble Vantastic" in a
      and not m["image"], (a, m["image"]))

# same-name films: the one with a poster
responser._IMAGE_MAP["poster"]["tt0002"] = "0001/poster2.jpg"
g.add((e("F3"), p("P345"), Literal("tt0002")))
a, m = ask(plain, "poster for Heat")
check("poster of the same-name film that has one", a == "image:0001/poster2" and m["image"]["entity_uri"] == str(e("F3")),
      (a, m["image"]))
try:
    a, m = ask(plain, "Recommend movies similar to Inception")
    check("recommendation route", m["route"] == "recommendation" and m["intent"] is None, (m["route"], m["intent"]))
except Exception as exc:  # the recommender may need data files; the route is what matters here
    check("recommendation route", plain.last_meta.get("route") == "recommendation", repr(exc))

# the tiny graph gives the recommender nothing to rank, so the trace shows the route taken
for q in ("something in the style of Christopher Nolan", "good westerns please", "fans of Christopher Nolan, what now?"):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            plain.generate_response(q, g)
    except Exception:  # the recommender may need data files; the route is what matters here
        pass
    trace = buf.getvalue()
    check(f"recommendation, not a filmography [{q}]", "Detected recommendation question" in trace
          and "answering with the filmography" not in trace.split("Detected recommendation")[0], trace[-300:])
# "Movies directed by X" with years is a filmography question, not a pseudo-recommendation to rewrite
a, m = ask(plain, "Movies directed by Christopher Nolan after 2012")
check("no request word: years kept", "Interstellar" in a and "Inception" not in a and m["rewritten"] is None,
      (a, m["rewritten"]))
check("pseudo name: capitalized words only", responser._pseudo_name("Spielberg in the", "Recommend Spielberg in the 80s")
      == "Spielberg" and responser._pseudo_name("Guillermo del Toro", "Films by Guillermo del Toro") == "Guillermo del Toro")

check("rec filter phrase: genre + decade",
      Responser._rec_filter_phrase(["horror film"], (1980, 1989)) == "horror films from 1980 to 1989")
check("rec filter phrase: none", Responser._rec_filter_phrase([], None) is None)
check("rec filter phrase: QIDs dropped", Responser._rec_filter_phrase(["Q123"], (None, 2000)) == "films until 2000")

a, m = ask(plain, "Christopher Nolan movies")
check("person + films stays a filmography", m["route"] == "factual" and "Inception" in a, (m["route"], a))

total = passed + failed
print(f"\n{passed}/{total} passed")
sys.exit(1 if failed else 0)
