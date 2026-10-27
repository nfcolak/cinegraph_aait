#!/usr/bin/env python3
"""
Checks for recommendation routing, seed-title extraction and facet similarity
(core/recommender.py). Pure text and small dicts: no graph, no dataset.

    env -u PYTHONPATH .venv/bin/python -B tests/test_recommend_routing.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.recommender import calculate_similarity, extract_movie_titles, is_recommendation_question  # noqa: E402


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

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
