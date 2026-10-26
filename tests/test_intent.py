#!/usr/bin/env python3
"""
Checks for the intent parser (core/intent.py). Pure text, no graph, no dataset.

    env -u PYTHONPATH .venv/bin/python -B tests/test_intent.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.intent import (  # noqa: E402
    CONF_HIGH, CONF_LOW, CONF_NONE, CONF_WEAK, RELATION_LEXICON, RELATIONS, Intent, parse_intent)

H, W, L, N = CONF_HIGH, CONF_WEAK, CONF_LOW, CONF_NONE

# question, kind, relation, mention, year, genre, quoted, confidence, number of parts
CASES = [
    # evidence list of proposal.md: relation not found
    ("Who scored The Dark Knight?", "fact", "composer", "The Dark Knight", None, None, False, H, 0),
    ("Who played in Pulp Fiction?", "fact", "cast member", "Pulp Fiction", None, None, False, H, 0),
    ("Who are the actors of Forrest Gump?", "fact", "cast member", "Forrest Gump", None, None, False, H, 0),
    ("Who shot Blade Runner?", "fact", "cinematographer", "Blade Runner", None, None, False, H, 0),
    ("Director of Heat?", "fact", "director", "Heat", None, None, False, H, 0),
    ("Heat director", "fact", "director", "Heat", None, None, False, H, 0),
    ("What year was Jaws released?", "fact", "publication date", "Jaws", None, None, False, H, 0),
    ("Who produced Pulp Fiction?", "fact", "producer", "Pulp Fiction", None, None, False, H, 0),
    ("Movies by Steven Spielberg", "films_of", "director", "Steven Spielberg", None, None, False, H, 0),
    # wrong relation
    ("Who wrote the soundtrack of Inception?", "fact", "composer", "Inception", None, None, False, H, 0),
    # subject span
    ("music for Jack Sparrow", "fact", "composer", "Jack Sparrow", None, None, False, W, 0),
    ("soundtrack of Inception", "fact", "composer", "Inception", None, None, False, H, 0),
    ("screenplay for Fight Club", "fact", "screenwriter", "Fight Club", None, None, False, H, 0),
    ("Who composed the music for the movie Interstellar?", "fact", "composer", "Interstellar", None, None, False, H, 0),
    ("Who wrote the screenplay for the film Interstellar?", "fact", "screenwriter", "Interstellar", None, None, False, H, 0),
    ("What genre is Alien?", "fact", "genre", "Alien", None, None, False, H, 0),
    ("Who composed the Batman movies?", "fact", "composer", "Batman", None, None, False, H, 0),
    ("Who directed the Harry Potter films?", "fact", "director", "Harry Potter", None, None, False, H, 0),
    ("Who directed Good Will Hunting and who starred in it?", "fact", "director", "Good Will Hunting", None, None, False, H, 1),
    # titles used by the evidence (linker side), still parsed by the intent
    ("Who directed Titanic?", "fact", "director", "Titanic", None, None, False, H, 0),
    ("Who directed Gladiater?", "fact", "director", "Gladiater", None, None, False, H, 0),
    ("Who directed Toy Story?", "fact", "director", "Toy Story", None, None, False, H, 0),
    ("Who directed The Lord of the Rings?", "fact", "director", "The Lord of the Rings", None, None, False, H, 0),
    ("Which movies did Nolan direct?", "films_of", "director", "Nolan", None, None, False, H, 0),
    # relation lexicon
    ("Who is the cinematographer of Dune?", "fact", "cinematographer", "Dune", None, None, False, H, 0),
    ("Who was the director of photography on Alien?", "fact", "cinematographer", "Alien", None, None, False, H, 0),
    ("Who is the composer of Gladiator?", "fact", "composer", "Gladiator", None, None, False, H, 0),
    ("Who wrote Casablanca?", "fact", "screenwriter", "Casablanca", None, None, False, H, 0),
    ("Who is the writer of Heat?", "fact", "screenwriter", "Heat", None, None, False, H, 0),
    ("Which company produced Toy Story?", "fact", "production company", "Toy Story", None, None, False, H, 0),
    ("What studio made Alien?", "fact", "production company", "Alien", None, None, False, H, 0),
    ("Which company distributed Heat?", "fact", "distributed by", "Heat", None, None, False, H, 0),
    ("Who is the producer of Se7en?", "fact", "producer", "Se7en", None, None, False, H, 0),
    ("Who is in the cast of Heat?", "fact", "cast member", "Heat", None, None, False, H, 0),
    ("Which actors starred in Heat?", "fact", "cast member", "Heat", None, None, False, H, 0),
    ("Who stars in Joker?", "fact", "cast member", "Joker", None, None, False, H, 0),
    ("Who made Heat?", "fact", "director", "Heat", None, None, False, H, 0),
    ("Who was Heat directed by?", "fact", "director", "Heat", None, None, False, H, 0),
    ("What awards was Heat nominated for?", "fact", "nominated for", "Heat", None, None, False, H, 0),
    ("What awards did Heat win?", "fact", "award received", "Heat", None, None, False, H, 0),
    ("What language is Parasite in?", "fact", "original language", "Parasite", None, None, False, H, 0),
    ("What country is Parasite from?", "fact", "country of origin", "Parasite", None, None, False, H, 0),
    ("What kind of movie is Alien?", "fact", "genre", "Alien", None, None, False, H, 0),
    ("When was Titanic released?", "fact", "publication date", "Titanic", None, None, False, H, 0),
    ("When did Get Out come out?", "fact", "publication date", "Get Out", None, None, False, H, 0),
    ("Release date of Heat", "fact", "publication date", "Heat", None, None, False, H, 0),
    # films_of forms
    ("Which movies did Christopher Nolan direct?", "films_of", "director", "Christopher Nolan", None, None, False, H, 0),
    ("What did Spielberg direct?", "films_of", "director", "Spielberg", None, None, False, H, 0),
    ("Films directed by Martin Scorsese", "films_of", "director", "Martin Scorsese", None, None, False, H, 0),
    ("Filmography of Christopher Nolan", "films_of", "director", "Christopher Nolan", None, None, False, H, 0),
    ("Steven Spielberg's films", "films_of", "director", "Steven Spielberg", None, None, False, H, 0),
    ("Which films star Keanu Reeves?", "films_of", "cast member", "Keanu Reeves", None, None, False, H, 0),
    ("Movies with Tom Hanks", "films_of", "cast member", "Tom Hanks", None, None, False, H, 0),
    ("Which films did Hans Zimmer compose music for?", "films_of", "composer", "Hans Zimmer", None, None, False, H, 0),
    ("Which movies were produced by Pixar?", "films_of", "production company", "Pixar", None, None, False, H, 0),
    ("Which movies were produced by Kathleen Kennedy?", "films_of", "producer", "Kathleen Kennedy", None, None, False, H, 0),
    ("Which comedy movies did Adam Sandler star in?", "films_of", "cast member", "Adam Sandler", None, "comedy", False, H, 0),
    ("Which horror movies were directed by James Wan?", "films_of", "director", "James Wan", None, "horror", False, H, 0),
    ("Which sci-fi films did Ridley Scott direct?", "films_of", "director", "Ridley Scott", None, "sci-fi", False, H, 0),
    # year hints
    ("Who directed Titanic (1953)?", "fact", "director", "Titanic", 1953, None, False, H, 0),
    ("Who directed the 1997 Titanic?", "fact", "director", "Titanic", 1997, None, False, H, 0),
    ("Who directed Titanic from 1953?", "fact", "director", "Titanic", 1953, None, False, H, 0),
    ("When was Titanic (1997) released?", "fact", "publication date", "Titanic", 1997, None, False, H, 0),
    ("Who directed 1917?", "fact", "director", "1917", None, None, False, H, 0),
    # sub-questions
    ("Who directed Pulp Fiction and who wrote it?", "fact", "director", "Pulp Fiction", None, None, False, H, 1),
    ("Who directed Heat, and when was it released?", "fact", "director", "Heat", None, None, False, H, 1),
    # lower case
    ("who directed the dark knight", "fact", "director", "the dark knight", None, None, False, H, 0),
    ("movies by steven spielberg", "films_of", "director", "steven spielberg", None, None, False, H, 0),
    ("who composed the music for inception", "fact", "composer", "inception", None, None, False, H, 0),
    ("what genre is alien", "fact", "genre", "alien", None, None, False, H, 0),
    # quoted titles, titles that contain relation words
    ('Who directed "The Dark Knight"?', "fact", "director", "The Dark Knight", None, None, True, H, 0),
    ('Who directed "Composer"?', "fact", "director", "Composer", None, None, True, H, 0),
    ('Who composed the music for "Music and Lyrics"?', "fact", "composer", "Music and Lyrics", None, None, True, H, 0),
    ("Who directed The Director?", "fact", "director", "The Director", None, None, False, H, 0),
    ("Who directed Music and Lyrics?", "fact", "director", "Music and Lyrics", None, None, False, H, 0),
    ("Who wrote Music and Lyrics?", "fact", "screenwriter", "Music and Lyrics", None, None, False, H, 0),
    ("Who produced The Producers?", "fact", "producer", "The Producers", None, None, False, H, 0),
    ("Who directed In Bruges?", "fact", "director", "In Bruges", None, None, False, H, 0),
    ("Who directed Schindler's List?", "fact", "director", "Schindler's List", None, None, False, H, 0),
    ("Who directed Do the Right Thing?", "fact", "director", "Do the Right Thing", None, None, False, H, 0),
    # confidence bands
    ("Who directed Up?", "fact", "director", "Up", None, None, False, W, 0),
    ("Who directed it?", "fact", "director", None, None, None, False, L, 0),
    ("Who directed?", "fact", "director", None, None, None, False, L, 0),
    # unknown
    ("Recommend a movie like Inception", "unknown", None, None, None, None, False, N, 0),
    ("Movies like Titanic", "unknown", None, None, None, None, False, N, 0),
    ("Show me Halle Berry", "unknown", None, None, None, None, False, N, 0),
    ("Who is Tom Hanks?", "unknown", None, None, None, None, False, N, 0),
    ("Hello", "unknown", None, None, None, None, False, N, 0),
    ("What is the capital of France?", "unknown", None, None, None, None, False, N, 0),
    ("Tell me a joke", "unknown", None, None, None, None, False, N, 0),
    ("", "unknown", None, None, None, None, False, N, 0),
]


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + detail))
    return cond


def run_case(case):
    q, kind, rel, mention, year, genre, quoted, conf, nparts = case
    got = parse_intent(q)
    want = (kind, rel, mention, year, genre, quoted, conf, nparts)
    have = (got.kind, got.relation, got.mention, got.year, got.genre, got.quoted, got.confidence, len(got.parts))
    return check(repr(q), have == want, f"want {want}, got {have}")


results = [run_case(c) for c in CASES]

# parts: relations, the "it" mention is inherited
g = parse_intent("Who directed Good Will Hunting and who starred in it?")
results.append(check("split: second part is cast member of the same mention",
                     len(g.parts) == 1 and g.parts[0].relation == "cast member"
                     and g.parts[0].mention == "Good Will Hunting" and g.parts[0].confidence == H))
g = parse_intent("Who directed Heat, and when was it released?")
results.append(check("split: date part inherits the mention",
                     g.parts[0].relation == "publication date" and g.parts[0].mention == "Heat"))
g = parse_intent("Who directed Romeo and Juliet?")
results.append(check("no split inside a title with 'and'", g.mention == "Romeo and Juliet" and not g.parts))
g = parse_intent("Who directed Beauty and the Beast and who wrote it?")
results.append(check("split after a title with 'and'", g.mention == "Beauty and the Beast" and len(g.parts) == 1))

# a quoted title keeps its case and the quoted flag
g = parse_intent("Who directed 'The Producers'?")
results.append(check("single quotes give a quoted mention", g.mention == "The Producers" and g.quoted))

# to_dict is JSON safe and keeps parts
import json  # noqa: E402
d = parse_intent("Who directed Good Will Hunting and who starred in it?").to_dict()
results.append(check("to_dict is JSON safe",
                     json.loads(json.dumps(d)) == d and d["parts"][0]["relation"] == "cast member"
                     and set(d) == {"kind", "relation", "mention", "quoted", "year", "genre", "confidence", "parts"}))
results.append(check("Intent defaults", Intent("unknown", None, None).confidence == 0.0
                     and Intent("unknown", None, None).parts == []))

# lexicon: every canonical relation has fragments, nothing else
results.append(check("lexicon keys equal RELATIONS", sorted(RELATION_LEXICON) == sorted(RELATIONS)))
results.append(check("lexicon fragments are non-empty", all(RELATION_LEXICON[r] for r in RELATIONS)))

# relation labels exist in core.relation.FALLBACK_PRED_URIS
from core.relation import FALLBACK_PRED_URIS  # noqa: E402
results.append(check("RELATIONS match FALLBACK_PRED_URIS", sorted(RELATIONS) == sorted(FALLBACK_PRED_URIS)))

# parse time over every test question (including the split and quote forms)
questions = [c[0] for c in CASES]
parse_intent(questions[0])  # warm up
worst = 0.0
total = 0.0
for q in questions:
    t = time.perf_counter()
    parse_intent(q)
    dt = (time.perf_counter() - t) * 1000
    total += dt
    worst = max(worst, dt)
print(f"parse time over {len(questions)} questions: mean {total / len(questions):.3f} ms, worst {worst:.3f} ms")
results.append(check("every parse takes under 1 ms", worst < 1.0, f"worst {worst:.3f} ms"))

print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
