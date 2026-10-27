#!/usr/bin/env python3
"""
Checks for recommendation routing, seed-title extraction and facet similarity
(core/recommender.py): pure text, small dicts and a small synthetic graph; no dataset.

    env -u PYTHONPATH .venv/bin/python -B tests/test_recommend_routing.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rdflib import Graph, Literal, URIRef  # noqa: E402
from rdflib.namespace import RDFS  # noqa: E402

import core.recommender as rec_module  # noqa: E402
from core.linker import get_linker  # noqa: E402
from core.recommender import (  # noqa: E402
    calculate_similarity, extract_constraints, extract_movie_titles, has_similarity_cue, is_recommendation_question,
    year_range,
)


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + detail))
    return cond


results = []

# question -> seed titles the extractor must return (all of these must route to recommendation)
RECS = [
    ("Similar movies to chicken little", ["chicken little"]),
    ("similar movies to Chicken Little", ["Chicken Little"]),
    ("Movies similar to Chicken Little", ["Chicken Little"]),
    ("Movies like Chicken Little", ["Chicken Little"]),
    ("Something like Chicken Little", ["Chicken Little"]),
    ("Chicken Little similar", ["Chicken Little"]),
    ("chiken little similar movies", ["chiken little"]),
    ("Shrek-like movies", ["Shrek"]),
    ("I liked Chicken Little, what else would I like?", ["Chicken Little"]),
    ("I loved Up, recommend something", ["Up"]),
    ("any recommendations similar to toy story?", ["toy story"]),
    ("More like Pulp Fiction please", ["Pulp Fiction"]),
    ("what to watch after Frozen", ["Frozen"]),
    ("I want to watch something similar to Alien", ["Alien"]),
    ("Movies like Star Wars", ["Star Wars"]),
    ("Films similar to When Harry Met Sally", ["When Harry Met Sally"]),
    ("Movies like Something's Gotta Give", ["Something's Gotta Give"]),
    ("movies like the matrix and blade runner", ["the matrix", "blade runner"]),
]
for q, want in RECS:
    got = extract_movie_titles(q)
    results.append(check(f"routes to recommendation: {q!r}", is_recommendation_question(q)))
    results.append(check(f"seeds of {q!r}", got == want, f"want {want}, got {got}"))

# recommendations without a seed film still route there (theme search)
for q in ["recommend me a comedy", "Recommend some horror movies", "Give me Disney movies"]:
    results.append(check(f"routes to recommendation: {q!r}", is_recommendation_question(q)))

# factual questions stay factual
for q in [
    "Who directed Heat?",
    "What is the genre of Alien?",
    "Which movies did Christopher Nolan direct?",
    "When was Titanic released?",
    "Who composed the music for Jack Sparrow?",
    "Who starred in films like Heat?",
]:
    results.append(check(f"stays factual: {q!r}", not is_recommendation_question(q)))

# facet similarity: one shared composer alone must not beat shared genres + studio
seed = {
    "genre": {"family", "comedy", "fantasy", "children"},
    "composer": {"John Debney"},
    "production_company": {"Disney Animation"},
    "director": {"Mark Dindal"},
    "country": {"US"},
}
composer_only = {"genre": {"biography", "drama"}, "composer": {"John Debney"}, "country": {"US"}}
same_style = {"genre": {"family", "comedy", "fantasy"}, "production_company": {"Disney Animation"}, "country": {"US"}}
a, b = calculate_similarity(seed, composer_only), calculate_similarity(seed, same_style)
results.append(check("shared genres + studio outrank a shared composer", b > a, f"composer-only {a:.3f}, same-style {b:.3f}"))
results.append(check("similarity stays in [0, 1]", 0 <= a <= 1 and 0 <= b <= 1))
results.append(check("identical profiles score 1", abs(calculate_similarity(seed, seed) - 1.0) < 1e-9))
results.append(check("empty seed scores 0", calculate_similarity({}, seed) == 0.0))

# ---- wordings that ask for suggestions without the usual "similar/like" phrasing ----
RECS2 = [
    ("I adored Paddington, what now?", ["Paddington"]),
    ("just watched Arrival... now what?", None),
    ("picks for lovers of Amelie", ["Amelie"]),
    ("anything else similar to Arrival?", ["Arrival"]),
    ("Is there anything else like Sicario?", ["Sicario"]),
    ("comedies like Superbad", ["Superbad"]),
    ("thrillers similar to Gone Girl", ["Gone Girl"]),
    ("something in the spirit of Spirited Away", ["Spirited Away"]),
    ("after Whiplash what do I watch", ["Whiplash"]),
    ("If I enjoyed Collateral and Drive, what should I see next?", ["Collateral", "Drive"]),
    ("something like zodiac but scarier", ["zodiac"]),
    ("anything like Fargo from the 90s?", ["Fargo"]),
    ("great horror flicks for a sleepover", []),
    ("some 90s comedies", []),
    ("a heartwarming film for the family", []),
    ("creepy movies to watch alone", []),
    ("recommend a movie released after 2015", []),
]
for q, want in RECS2:
    results.append(check(f"routes to recommendation: {q!r}", is_recommendation_question(q)))
    if want is not None:
        got = extract_movie_titles(q)
        results.append(check(f"seeds of {q!r}", got == want, f"want {want}, got {got}"))

# still factual, or a title rather than a theme
for q in [
    "Who are the fans of Star Wars called?",
    "When did the 80s classic Back to the Future come out?",
    "Which actor starred in the musical La La Land?",
    "How many romantic movies did Meg Ryan make?",
    "Top Gun movies",
    "Good Will Hunting release date",
]:
    results.append(check(f"not a seedless recommendation: {q!r}", not is_recommendation_question(q)))

# constraints: the seed title is no constraint, modifiers and decades are
c = extract_constraints("films like War Horse")
results.append(check("seed title gives no genre (War Horse)", "genres" not in c, str(c)))
c = extract_constraints("movies like 1917")
results.append(check("seed title gives no years (1917)", "years" not in c, str(c)))
c = extract_constraints("something like Zodiac but funnier")
results.append(check("'but funnier' asks for comedy", c.get("genres") == ["comedy"], str(c)))
c = extract_constraints("thrillers like Heat from the 90s")
results.append(check("decade after a seed is a year range", c.get("years") == (1990, 1999), str(c)))
results.append(check("plural genre noun is a genre", "thriller" in (c.get("genres") or []), str(c)))
for text, want in [("80s movies", (1980, 1989)), ("films from the 1970s", (1970, 1979)), ("before 1960", (None, 1959)),
                   ("after 2012", (2013, None)), ("between 1995 and 2005", (1995, 2005)), ("best movies of 1994", (1994, 1994)),
                   ("the 2000s", (2000, 2009)), ("comedies", None)]:
    results.append(check(f"year_range({text!r})", year_range(text) == want, f"got {year_range(text)}"))

# similarity cue (decides recommendation vs filmography for a named person)
for q, want in [("Movies in the style of Ava Lindqvist", True), ("for fans of Ava Lindqvist", True),
                ("Ava Lindqvist movies", False), ("What did Ava Lindqvist direct?", False)]:
    results.append(check(f"has_similarity_cue({q!r}) is {want}", has_similarity_cue(q) == want))

# seedless theme requests: a name found in them is a false match (filmography must not take over)
for q, want in [("good westerns please", True), ("top 80s thrillers", True), ("Suggest a creepy movie for tonight", True),
                ("great animated films", True), ("films from the 70s", True),
                ("best Ava Lindqvist movies", False), ("good movies like Fargo", False), ("Top Gun movies", False)]:
    results.append(check(f"is_theme_request({q!r}) is {want}", rec_module.is_theme_request(q) == want))

# ---- recommender on a small synthetic graph (linker built, no embeddings) ----
WD, P = "http://www.wikidata.org/entity/", "http://www.wikidata.org/prop/direct/"
g = Graph()
labels = {}


def e(q):
    return URIRef(WD + q)


def ent(q, label, cls, year=None):
    labels[e(q)] = label
    g.add((e(q), RDFS.label, Literal(label)))
    g.add((e(q), URIRef(P + "P31"), e(cls)))
    if year:
        g.add((e(q), URIRef(P + "P577"), Literal(f"{year}-01-01")))


def film(q, label, year, genres, *links):
    ent(q, label, "Q11424", year)
    for gq in genres:
        g.add((e(q), URIRef(P + "P136"), e(gq)))
    g.add((e(q), URIRef(P + "P495"), e("US")))
    for prop, obj in links:
        g.add((e(q), URIRef(P + prop), e(obj)))


for gq, glabel in [("Gcrime", "crime film"), ("Gcom", "comedy film"), ("Ghor", "horror film"), ("Gfam", "family film"),
                   ("Gmus", "musical film"), ("Grom", "romance film"), ("Gthr", "thriller film")]:
    ent(gq, glabel, "Q483394")
ent("US", "United States", "Q6256")
ent("D1", "Ava Lindqvist", "Q5")
ent("D2", "Bruno Okafor", "Q5")
ent("A1", "Mira Sol", "Q5")
ent("C1", "Kite Animation", "Q1762059")
ent("S1", "Rocket Pup saga", "Q24856")
film("F1", "Glass Harbor", 1985, ["Gcrime", "Gthr"], ("P57", "D1"), ("P161", "A1"))
film("F2", "Night Ledger", 1988, ["Gcrime", "Gthr"], ("P57", "D1"))
film("F3", "Cold Meridian", 1992, ["Gcrime"], ("P57", "D1"))
film("F4", "Iron Alley", 1990, ["Gcrime", "Gthr"], ("P57", "D2"), ("P161", "A1"))
film("F5", "Silent Wharf", 2001, ["Gcrime", "Gthr"], ("P57", "D2"))
film("F6", "Pickle Parade", 1999, ["Gcom"])
film("F7", "Laughing Gas Station", 2003, ["Gcom", "Gcrime"], ("P161", "A1"))
film("F8", "Hollow Attic", 1982, ["Ghor"])
film("F9", "Crawlspace", 2010, ["Ghor"])
film("F10", "Bubble Town", 2004, ["Gfam"], ("P272", "C1"))
for q, label, y in [("F11", "Rocket Pup", 2000), ("F12", "Rocket Pup 2", 2002), ("F13", "Rocket Pup 3", 2005),
                    ("F14", "Rocket Pup: Lost Moon", 2008)]:
    film(q, label, y, ["Gfam"], ("P272", "C1"), ("P179", "S1"))
film("F15", "Moon Garden", 2006, ["Gfam"], ("P272", "C1"))
film("F16", "Paper Kite", 2007, ["Gfam"], ("P272", "C1"))
film("F17", "Starlight Avenue", 2016, ["Gmus", "Grom"])
film("F18", "Tap Shoes Tango", 1995, ["Gmus"])
film("F19", "Rainy Kiss", 2014, ["Grom"])
film("F20", "Salt and Ember", 1997, ["Gcrime"])
film("F21", "Salt", 2010, ["Gthr"])
get_linker(g, labels)


def recs(titles, k=4, **kw):
    return [t for t, _s in rec_module.recommend_movies(g, titles, top_k=k, **kw)]


got = recs(["Bubble Town"], k=4)
pups = [t for t in got if t.startswith("Rocket Pup")]
results.append(check("at most two films of one franchise in the top 4", len(pups) <= 2, str(got)))
results.append(check("other films of the studio fill the list", {"Moon Garden", "Paper Kite"} <= set(got), str(got)))

got = recs(["Ava Lindqvist's"], k=3)
results.append(check("a director as taste: seeds are her films",
                     set(rec_module.LAST_RUN["seeds"]) == {WD + "F1", WD + "F2", WD + "F3"}, str(rec_module.LAST_RUN["seeds"])))
results.append(check("a director as taste: none of her films recommended",
                     not {"Glass Harbor", "Night Ledger", "Cold Meridian"} & set(got), str(got)))
results.append(check("a director as taste: crime films recommended", "Iron Alley" in got, str(got)))
results.append(check("a director as taste: shown as her films",
                     rec_module.LAST_RUN["seed_names"] == ["Ava Lindqvist's films"], str(rec_module.LAST_RUN["seed_names"])))
recs(["Ava Lindqvist films"], k=3)
results.append(check("'<name> films' as taste", len(rec_module.LAST_RUN["seeds"]) == 3, str(rec_module.LAST_RUN["seeds"])))
recs(["ava lindqvst"], k=3)
results.append(check("typo'd director as taste", len(rec_module.LAST_RUN["seeds"]) == 3, str(rec_module.LAST_RUN["seeds"])))

pup_items = [("Rocket Pup", WD + "F11"), ("Rocket Pup 2", WD + "F12"), ("Rocket Pup 3", WD + "F13"), ("Moon Garden", WD + "F15")]
order = [t for t, _u in rec_module._diversify(g, pup_items, lambda x: x[0], lambda x: x[1])]
results.append(check("diversify moves the third franchise film back", order[2] == "Moon Garden", str(order)))
order = [t for t, _u in rec_module._diversify(g, pup_items, lambda x: x[0], lambda x: x[1], {"series:" + WD + "S1", "stem:rocket pup"})]
results.append(check("the franchise the user named is not capped", order == [t for t, _u in pup_items], str(order)))

recs(["Rocket Pup saga"], k=3)
results.append(check("a series as seed stands for its films", len(rec_module.LAST_RUN["seeds"]) == 4, str(rec_module.LAST_RUN["seeds"])))

got = [t for t, _s in rec_module.recommend_movies_with_constraints(g, ["Glass Harbor"], {"genres": ["comedy"]}, top_k=3)]
results.append(check("'like Glass Harbor but funnier' gives comedies only",
                     bool(got) and all(t in {"Pickle Parade", "Laughing Gas Station"} for t in got), str(got)))
results.append(check("the funnier variant still reports its seed", rec_module.LAST_RUN["seeds"] == [WD + "F1"],
                     str(rec_module.LAST_RUN["seeds"])))
got = [t for t, _s in rec_module.recommend_movies_with_constraints(g, ["Glass Harbor"], {"years": (1986, 1995)}, top_k=3)]
results.append(check("a decade constraint keeps films of those years", bool(got) and set(got) <= {"Night Ledger", "Cold Meridian", "Iron Alley"},
                     str(got)))

results.append(check("'Salt' + 'Ember' rejoin to the film 'Salt and Ember'",
                     rec_module._regroup_titles(g, ["Salt", "Ember"]) == ["Salt and Ember"]))
results.append(check("'Glass Harbor and Iron Alley' splits into two films",
                     rec_module._regroup_titles(g, ["Glass Harbor and Iron Alley"]) == ["Glass Harbor", "Iron Alley"]))
results.append(check("a real 'and' title stays whole", rec_module._regroup_titles(g, ["Salt and Ember"]) == ["Salt and Ember"]))


def theme(q, k=6):
    return [t for t, _s in rec_module.recommend_by_theme(g, q, top_k=k)]


got = theme("anything creepy this evening")
results.append(check("mood 'scary' -> horror films", set(got) == {"Hollow Attic", "Crawlspace"}, str(got)))
got = theme("a feel-good film")
results.append(check("mood 'feel-good' -> comedy/family/musical films", len(got) >= 3
                     and not {"Hollow Attic", "Crawlspace", "Glass Harbor", "Iron Alley"} & set(got), str(got)))
got = theme("80s horror")
results.append(check("decade + genre", got == ["Hollow Attic"], str(got)))
results.append(check("theme search reports its genres and years",
                     rec_module.LAST_RUN["theme"].get("years") == (1980, 1989)
                     and "horror film" in rec_module.LAST_RUN["theme"].get("genres", []), str(rec_module.LAST_RUN["theme"])))
got = theme("movies from the 1990s", k=10)
results.append(check("decade only", bool(got) and set(got) <= {"Cold Meridian", "Iron Alley", "Pickle Parade", "Tap Shoes Tango",
                                                               "Salt and Ember"}, str(got)))
got = theme("musicals please")
results.append(check("plural genre noun 'musicals'", set(got) == {"Starlight Avenue", "Tap Shoes Tango"}, str(got)))
results.append(check("nothing themed -> no list", theme("something for my grandmother") == []))

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
