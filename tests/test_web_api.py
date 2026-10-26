#!/usr/bin/env python3
"""
Checks for the web API reply shaping (server/api.py).

Needs rdflib, numpy and fastapi (server/requirements.txt) but no dataset: the graph
is not loaded, so entity cards are skipped and only the reply logic is exercised.

    python3 -B tests/test_web_api.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.api import build_reply, tmdb_url, _tidy_sparql  # noqa: E402


def meta(**kw):
    base = {"route": None, "entity_uri": None, "relation": None, "property_uri": None, "inverse": False,
            "sparql": None, "answer_uris": [], "seeds": [], "recommendations": [], "image": None, "rewritten": None}
    base.update(kw)
    return base


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    return cond


results = []

results.append(check("poster path maps to TMDB w500",
                     tmdb_url("0344/knLBjlWP36OSu1A0Btbyy9r1WXH", "poster")
                     == "https://image.tmdb.org/t/p/w500/knLBjlWP36OSu1A0Btbyy9r1WXH.jpg"))
results.append(check("scene path maps to TMDB w1280 and keeps extension",
                     tmdb_url("0000/abc.jpg", "backdrop_cast") == "https://image.tmdb.org/t/p/w1280/abc.jpg"))

r = build_reply("Show me Halle Berry", "image:0344/knLB", meta(route="multimedia", image={"kind": "profile", "entity_label": "Halle Berry"}), "", 4)
results.append(check("image answer becomes an image, not text", r["image"]["kind"] == "profile" and r["answer"] == "" and r["ok"]))

r = build_reply("x", "backdrop_cast", meta(route="multimedia", image={"kind": "backdrop_cast"}), "", 1)
results.append(check("multimedia without image is a miss", not r["ok"]))

r = build_reply("x", "image:0001/h", meta(route="multimedia", image={"kind": "backdrop_cast", "entity_label": "Brad Pitt"}), "", 1)
results.append(check("actor scene is labelled 'scene'", r["image"]["kind"] == "scene"))

r = build_reply("Who directed Galaxy Quest?",
                "The movie was directed by Gustaf Tenggren (type: Q5). (Note: This is a prediction based on similar movies, because no factual answer was available in the knowledge graph.)",
                meta(route="prediction", relation="director"), "", 50)
results.append(check("prediction note and type are split off",
                     r["answer"] == "The movie was directed by Gustaf Tenggren." and r["note"].startswith("This is a prediction")))

r = build_reply("asdf", "Could not parse relation for embedding query.", meta(route="prediction"), "", 0)
results.append(check("failure text is a miss", not r["ok"]))

r = build_reply("Who directed Inception?", "The movie was directed by Christopher Nolan.", meta(route="factual", relation="director",
                property_uri="http://www.wikidata.org/prop/direct/P57"), "[responser] Factual query took 0.004s\n[data] noise\nplain line", 4)
results.append(check("factual reply keeps property id and filters the log",
                     r["ok"] and r["property"] == "P57" and r["trace"] == ["[responser] Factual query took 0.004s"]))

r = build_reply("Which movies did Christopher Nolan direct?",
                "Movies directed by Christopher Nolan include A and B and Q190525 and C and D.",
                meta(route="factual", inverse=True, answer_uris=[f"http://www.wikidata.org/entity/Q{i}" for i in range(5)]), "", 5)
results.append(check("long list answer is summarized with its count",
                     r["answer"] == "Movies directed by Christopher Nolan: 5 titles in the graph."))
r = build_reply("x", "A and B and C and D", meta(route="factual", answer_uris=["u1", "u2", "u3", "u4"]), "", 5)
results.append(check("list without a sentence head becomes a count", r["answer"] == "4 entries in the graph."))
r = build_reply("What genre is Alien?", "The genres are A and B and C and D.",
                meta(route="factual", answer_uris=["u1", "u2", "u3", "u4"]), "", 5)
results.append(check("'X are ...' list keeps its head", r["answer"] == "The genres: 4 entries in the graph."))
r = build_reply("Who played in Pulp Fiction?", 'The cast of "Pulp Fiction" includes A and B and C and D.',
                meta(route="factual", answer_uris=["u1", "u2", "u3", "u4"]), "", 5)
results.append(check("'X includes ...' list keeps its head",
                     r["answer"] == 'The cast of "Pulp Fiction": 4 entries in the graph.'))
mp = [{"relation": "director", "answer": "The movie was directed by G."},
      {"relation": "cast member", "answer": "The cast includes A and B and C and D."}]
mp_text = "The movie was directed by G. The cast includes A and B and C and D."
r = build_reply("Who directed X and who starred in it?", mp_text,
                meta(route="factual", parts=mp, answer_uris=["u0", "u1", "u2", "u3", "u4"]), "", 5)
results.append(check("multi-part answer is never collapsed to a count", r["answer"] == mp_text))
r = build_reply("x", "The movie was directed by A and B.", meta(route="factual", answer_uris=["u1", "u2"]), "", 5)
results.append(check("short answers stay as written", r["answer"] == "The movie was directed by A and B."))

r = build_reply("Who directed Harry Potter?",
                "The movie was directed by Q106542729 (type: Q5). (Note: This is a prediction based on similar movies, because no factual answer was available in the knowledge graph.)",
                meta(route="prediction", relation="director"), "", 100)
results.append(check("prediction that is only a bare Q-ID is not an answer", not r["ok"] and "Q106542729" not in r["answer"]))

# --- intent metadata: via_films, alternatives, reading, parts ---
from server.api import STATE  # noqa: E402


class _StubCatalog:
    film_by_qid = {f"Q{i}": {"qid": f"Q{i}", "label": f"Film {i}", "year": "200%d" % i, "_key": f"film {i}"} for i in (1, 2)}

    @staticmethod
    def _public(row):
        return {k: v for k, v in row.items() if not k.startswith("_")}

    @staticmethod
    def list_films(*_a, **_k):
        return {"films": [{"qid": "Q9", "label": "Similar"}]}


WDU = "http://www.wikidata.org/entity/"
intent = {"kind": "fact", "relation": "director", "mention": "Jack Sparrow", "parts": []}

STATE.catalog = _StubCatalog()
text = "Captain Jack Sparrow is not a film itself; the graph links it to 2 films. The director of those films: A (2 films)."
r = build_reply("Who directed Jack Sparrow?", text,
                meta(route="factual", relation="director", intent=intent, subject_kind="character",
                     via_films=[WDU + "Q1", WDU + "Q2", WDU + "Q404"], answer_uris=[WDU + "Q7"]), "", 5)
results.append(check("via_films become film suggestions with a title",
                     [s["qid"] for s in r["suggestions"]] == ["Q1", "Q2"] and r["suggestions_title"] == "Films linked to Jack Sparrow"))
results.append(check("answer text is not rewritten by the server", r["answer"] == text and r["ok"] and r["route"] == "factual"))
results.append(check("reading carries relation, kind and via count",
                     r["reading"] == {"relation": "director", "subject": "Jack Sparrow", "subject_kind": "character",
                                      "via_count": 3, "parts": []}))

alts = [{"uri": WDU + "Q5", "qid": "Q5", "label": "Titanic", "year": 1997, "kind": "film"},
        {"uri": WDU + "Q6", "qid": "Q6", "label": "Titanic", "year": 1953, "kind": "film"}]
r = build_reply("Who directed Titanic?", "The movie was directed by X.",
                meta(route="factual", relation="director", intent={**intent, "mention": "Titanic"}, alternatives=alts), "", 5)
results.append(check("alternatives rewrite the title in the question",
                     [a["ask"] for a in r["alternatives"]] == ["Who directed Titanic (1997)?", "Who directed Titanic (1953)?"]
                     and r["alternatives"][0]["qid"] == "Q5" and r["alternatives"][0]["year"] == 1997))

r = build_reply("titanic director", "x", meta(route="factual", alternatives=alts[:1],
                intent={**intent, "mention": "titanic"}), "", 5)
results.append(check("alternative title match is case-insensitive", r["alternatives"][0]["ask"] == "Titanic (1997) director"))

parts = [{"relation": "director", "entity_uri": WDU + "Q1", "answer_uris": [], "answer": "A"},
         {"relation": "cast member", "entity_uri": WDU + "Q1", "answer_uris": [], "answer": "B"}]
r = build_reply("Good Will Hunting and who starred in it", "A. B.", meta(route="factual", intent=intent, parts=parts), "", 5)
results.append(check("reading lists every sub-question", [p["relation"] for p in r["reading"]["parts"]] == ["director", "cast member"]))

r = build_reply("Who directed Inception?", "The movie was directed by Christopher Nolan.", meta(route="factual", relation="director"), "", 5)
results.append(check("no intent: reading is null, no alternatives, no via suggestions",
                     r["reading"] is None and r["alternatives"] == [] and r["suggestions"] == []))
r = build_reply("x", "The movie was directed by A.", meta(route="factual", intent=intent, relation="director"), "", 5)
results.append(check("answer without via_films has zero via_count", r["reading"]["via_count"] == 0))
STATE.catalog = None

q = """
    PREFIX wd: <http://www.wikidata.org/entity/>
    SELECT ?obj WHERE {
      wd:Q1 <p> ?obj .  # comment
    }
"""
results.append(check("SPARQL is shown without prefixes and comments", _tidy_sparql(q) == "SELECT ?obj WHERE {\n  wd:Q1 <p> ?obj .\n}"))

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
