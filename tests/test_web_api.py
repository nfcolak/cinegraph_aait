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
results.append(check("list without a sentence head becomes a count", r["answer"] == "4 titles in the graph."))
r = build_reply("x", "The movie was directed by A and B.", meta(route="factual", answer_uris=["u1", "u2"]), "", 5)
results.append(check("short answers stay as written", r["answer"] == "The movie was directed by A and B."))

r = build_reply("Who directed Harry Potter?",
                "The movie was directed by Q106542729 (type: Q5). (Note: This is a prediction based on similar movies, because no factual answer was available in the knowledge graph.)",
                meta(route="prediction", relation="director"), "", 100)
results.append(check("prediction that is only a bare Q-ID is not an answer", not r["ok"] and "Q106542729" not in r["answer"]))

q = """
    PREFIX wd: <http://www.wikidata.org/entity/>
    SELECT ?obj WHERE {
      wd:Q1 <p> ?obj .  # comment
    }
"""
results.append(check("SPARQL is shown without prefixes and comments", _tidy_sparql(q) == "SELECT ?obj WHERE {\n  wd:Q1 <p> ?obj .\n}"))

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
