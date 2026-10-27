#!/usr/bin/env python3
"""
Checks for the holdout and review fixes of the question-robustness change (group 8), plus direct
tests of helpers the code review listed as untested. One small synthetic graph; wordings are not
taken from any question set.

No dataset needed (ratings and image caches are stubbed); runs in seconds.

    env -u PYTHONPATH .venv/bin/python -B tests/test_review_fixes.py
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

import core.intent as intent_mod  # noqa: E402
import core.recommender as rec  # noqa: E402
import core.responser as responser  # noqa: E402
from core.entity import resolve_entity  # noqa: E402
from core.filmography import Filmography, mask_names, years_of, _in_name_run  # noqa: E402
from core.intent import parse_intent, year_span  # noqa: E402
from core.linker import EntityLinker, _aligned, _one_edit, get_linker  # noqa: E402
from core.responser import Responser, is_multimedia_query  # noqa: E402
from server.api import _summarize_list  # noqa: E402

responser._IMAGE_MAP.update({"poster": {}, "profile": {"nm0000901": "pf/ava.jpg"}})

WD = "http://www.wikidata.org/entity/"
P = "http://www.wikidata.org/prop/direct/"
FILM, HUMAN, CHAR, SERIES, TV, COMPANY = "Q11424", "Q5", "Q15773347", "Q24856", "Q5398426", "Q1762059"


def e(q):
    return URIRef(WD + q)


def p(x):
    return URIRef(P + x)


g = Graph()


def ent(q, label, cls=None, date=None):
    g.add((e(q), RDFS.label, Literal(label, lang="en")))
    if cls:
        g.add((e(q), p("P31"), e(cls)))
    if date:
        g.add((e(q), p("P577"), Literal(date)))


def link(a, rel, b):
    g.add((e(a), p(rel), e(b)))


# a film with crew, cast, characters and a performer link
ent("F1", "Brazil", FILM, "1985-02-20")
ent("D1", "Terry Gilliam", HUMAN)
ent("A1", "Jonathan Pryce", HUMAN)
ent("A2", "Ian Holmes", HUMAN)
ent("M1", "Michael Kamen", HUMAN)
ent("W1", "Tom Stoppard", HUMAN)
ent("CH1", "Sam Lowry", CHAR)
link("F1", "P57", "D1"); link("F1", "P161", "A1"); link("F1", "P161", "A2")
link("F1", "P86", "M1"); link("F1", "P58", "W1"); link("F1", "P674", "CH1")
link("CH1", "P175", "A1")
# a character without performer links
ent("F3", "Moon", FILM, "2009-06-12")
ent("A3", "Sam Rockwall", HUMAN)
ent("CH5", "Lonely Ghost", CHAR)
ent("AW1", "Hugo Award for Best Dramatic Presentation")
link("F3", "P161", "A3"); link("F3", "P674", "CH5"); link("F3", "P1411", "AW1")
# characters of a film, its country
ent("F2", "Paprika", FILM, "2006-11-25")
ent("CH2", "Detective Konakawa", CHAR)
ent("CY1", "Japan")
link("F2", "P674", "CH2"); link("F2", "P495", "CY1")
# a company whose name holds a genre word, one animated film, one TV series
ent("CO1", "Sunrise Animation Studios", COMPANY)
ent("GA", "animated film")
ent("F4", "Cowboy Tale", FILM, "1998-04-03")
ent("F5", "Star Road", FILM, "2001-05-01")
ent("T1", "Sunrise Hour", TV)
link("F4", "P272", "CO1"); link("F5", "P272", "CO1"); link("T1", "P272", "CO1"); link("F4", "P136", "GA")
# a company with no company word in its name
ent("CO2", "Aardvark", COMPANY)
ent("F6", "Clay Days", FILM, "2000-01-01")
link("F6", "P272", "CO2")
# shared films with roles: a director, his actor and his composer
ent("TB", "Tim Barton", HUMAN)
ent("JD", "Johnny Deep", HUMAN)
ent("DE", "Danny Elfmann", HUMAN)
ent("XX", "Gore Verbinsky", HUMAN)
for f, label, year in (("F7", "Sleepy Town", "1999"), ("F8", "Big Fish Tale", "2003"), ("F9", "Pirate Bay", "2003"),
                       ("F10", "Red Sky", "2004")):
    ent(f, label, FILM, f"{year}-01-01")
for f in ("F7", "F8"):
    link(f, "P57", "TB"); link(f, "P161", "JD"); link(f, "P86", "DE")
link("F9", "P57", "XX"); link("F9", "P161", "JD"); link("F9", "P86", "DE")
link("F10", "P57", "XX"); link("F10", "P86", "DE")
link("F9", "P161", "TB")   # the director acted once in another's film
# two people in mixed roles: director + cast, cast + cast
ent("CE", "Clint Westwood", HUMAN)
ent("MF", "Morgan Freedman", HUMAN)
ent("F11", "Gold Plain", FILM, "1992-01-01")
ent("F12", "Baby Fight", FILM, "2004-01-01")
link("F11", "P57", "CE"); link("F11", "P161", "MF"); link("F12", "P161", "CE"); link("F12", "P161", "MF")
# a film series and a film only "inspired by" it
ent("SER1", "Max Road", SERIES)
ent("F13", "Max Road One", FILM, "1979-01-01")
ent("F14", "Max Road Two", FILM, "1981-01-01")
ent("F15", "Water Planet", FILM, "1995-01-01")
ent("D4", "George Millar", HUMAN)
ent("D5", "Kevin Reynold", HUMAN)
link("F13", "P179", "SER1"); link("F14", "P179", "SER1"); link("F15", "P941", "SER1")
link("F13", "P57", "D4"); link("F14", "P57", "D4"); link("F15", "P57", "D5")
# a director known by surname with five films
ent("HC", "Alfred Hitchcock", HUMAN)
for i in range(16, 21):
    ent(f"F{i}", f"Suspense Story {i}", FILM, f"19{i + 40}-01-01")
    link(f"F{i}", "P57", "HC")
# real words around namesakes: "will" and "kids" are in three labels each
ent("F21", "Will Penny", FILM)
ent("F22", "Good Will Hunting", FILM)
ent("F23", "Free Will", FILM)
ent("F24", "Kids Return", FILM)
ent("F25", "Spy Kids", FILM)
ent("F26", "Kids Again", FILM)
ent("WS", "Willow Smyth", HUMAN)
link("F21", "P161", "WS")
ent("GK", "GKIDS", COMPANY)
link("F26", "P750", "GK")
ent("WF", "Will Ferral", HUMAN)
link("F25", "P161", "WF")
# a person with a picture
ent("AV", "Ava Doe", HUMAN)
g.add((e("AV"), p("P345"), Literal("nm0000901")))
link("F22", "P161", "AV")
# an entity typed by use only (no class): the production company of a film
g.add((e("U1"), RDFS.label, Literal("Bright Works", lang="en")))
link("F6", "P272", "U1")
# accents in a label
ent("F27", "Amélie Story", FILM, "2001-04-25")

labels = {s: str(o) for s, o in g.subject_objects(RDFS.label)}
L = EntityLinker(g, labels)
F = Filmography(g, L)
plain = Responser()

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS {name}")
    else:
        failed += 1
        print(f"FAIL {name}  {detail}")


def ask(q):
    with contextlib.redirect_stdout(io.StringIO()):
        a = plain.generate_response(q, g)
    return a or "", plain.last_meta


def lab(uris):
    return {labels.get(URIRef(u)) for u in uris}


# --- one year-range reader (H1, M3) ---
for text, want in [("Gilliam films from 1985", (1985, 1985)), ("released in 1985", (1985, 1985)),
                   ("since 1985", (1985, None)), ("after 1985", (1986, None)), ("later than 2001", (2002, None)),
                   ("until 1990", (None, 1990)), ("before 1990", (None, 1989)), ("from 1990 onwards", (1990, None)),
                   ("in the mid 70s", (1974, 1976)), ("early 60s", (1960, 1963)), ("late 60s", (1967, 1969)),
                   ("the 80's", (1980, 1989)), ("from the seventies", (1970, 1979)), ("between 2001 and 1999", (1999, 2001)),
                   ("Blade Walker 2049", None), ("2001: A Space Trip", None)]:
    got = year_span(text)
    check(f"year_span({text!r})", (got[:2] if got else None) == want, f"got {got}")
check("filmography and recommender read years like the parser",
      years_of("comedies from 1985")[:2] == rec.year_range("comedies from 1985") == (1985, 1985))
seg, lo, hi = intent_mod._take_range("Terry Gilliam movies from the late 80s")
check("_take_range moves the decade out", (seg, lo, hi) == ("Terry Gilliam movies", 1987, 1989), (seg, lo, hi))
it = parse_intent("Terry Gilliam films from 1985")
check("parser: 'from <year>' is that year", (it.year_from, it.year_to) == (1985, 1985), it.to_dict())

# --- typo targets from the relation lexicon (M2) ---
for word, want in [("genere", "genre"), ("langauge", "language"), ("countyr", "country"), ("nominatoins", "nominations"),
                   ("directer", "directed"), ("staring", None), ("scarred", None), ("county", None),
                   ("player", None), ("helmet", None)]:
    got = intent_mod._fix_typo(word)
    check(f"_fix_typo({word!r})", got == want if want else got is None, f"got {got}")
check("typo targets hold genre/country/language/awards",
      {"genre", "country", "language", "awards"} <= set(intent_mod._TYPO_TARGETS))
check("_denoise fixes a relation-word typo", intent_mod._denoise("whats the genere of Brazil") ==
      "what is the genre of Brazil", intent_mod._denoise("whats the genere of Brazil"))

# --- chat words only stand alone (M4) ---
check("_denoise keeps 'u-571'", "u-571" in intent_mod._denoise("who directed u-571"))
check("_denoise keeps 'R. Lee'", intent_mod._denoise("films with r. lee ermey") == "films with r. lee ermey")
check("_denoise still expands a lone 'u'", intent_mod._denoise("can u tell me") == "can you tell me")
check("_denoise drops emoji and repeated marks", intent_mod._denoise("who scored Brazil 🎬🎬 ??!") == "who scored Brazil ?")

# --- no title list in the company hint (M1) ---
check("_COMPANY_HINT names no single studio of the sets", intent_mod._COMPANY_HINT.search("Ghibli") is None)

# --- new question forms ---
for q, want in [
    ("where was Paprika from", dict(kind="fact", relation="country of origin", mention="Paprika")),
    ("where does Brazil come from?", dict(kind="fact", relation="country of origin", mention="Brazil")),
    ("was Moon nominated for anything", dict(kind="fact", relation="nominated for", mention="Moon")),
    ("Moon got nominated for which prizes?", dict(kind="fact", relation="nominated for", mention="Moon")),
    ("brazil screenplay by", dict(kind="fact", relation="screenwriter", mention="brazil")),
    ("which characters appear in Paprika?", dict(kind="fact", relation="characters", mention="Paprika")),
    ("who are the main characters of Brazil", dict(kind="fact", relation="characters", mention="Brazil")),
    ("What has Aardvark released?", dict(kind="films_of", mention="Aardvark")),
    ("What has Sunrise Pictures put out?", dict(kind="films_of", relation="production company")),
    ("what year was Moon released", dict(kind="fact", relation="publication date", mention="Moon")),
    ("What films did Will Ferral appear in?", dict(kind="films_of", relation="cast member", mention="Will Ferral")),
    ("films Tim Barton made with Johnny Deep", dict(kind="shared", relation="director", mention="Tim Barton")),
    ("which films did Danny Elfmann score for Tim Barton", dict(kind="shared", relation="composer")),
]:
    d = parse_intent(q).to_dict()
    check(f"parse {q!r}", all(d.get(k) == v for k, v in want.items()), {k: d.get(k) for k in want})
check("'for kids' is no second person", parse_intent("films Tim Barton made for kids").kind != "shared")
d = parse_intent("films Tim Barton made with Johnny Deep").to_dict()
check("'made with Y': Y as cast member", [(x["relation"], x["mention"]) for x in d["parts"]] ==
      [("cast member", "Johnny Deep")], d["parts"])
d = parse_intent("which films did Danny Elfmann score for Tim Barton").to_dict()
check("'scored for Y': Y as director", [(x["relation"], x["mention"]) for x in d["parts"]] ==
      [("director", "Tim Barton")], d["parts"])
d = parse_intent("Who directed Brazil and who composed the music?").to_dict()
check("'the music' in a later part is the first part's film",
      d["mention"] == "Brazil" and [(x["relation"], x["mention"]) for x in d["parts"]] == [("composer", "Brazil")], d)
d = parse_intent("Who composed The Score?").to_dict()
check("a capitalized 'The Score' stays a title", d["mention"] == "The Score", d)
d = parse_intent("brazil - director and composer?").to_dict()
check("title first, noun list after", d["mention"] == "brazil" and d["relation"] == "director"
      and [(x["relation"], x["mention"]) for x in d["parts"]] == [("composer", "brazil")], d)
check("_expand_nouns: title first", intent_mod._expand_nouns("Moon: genre and language") ==
      ["genre of Moon", "language of Moon"], intent_mod._expand_nouns("Moon: genre and language"))
check("_expand_nouns: list then title", intent_mod._expand_nouns("the director and writer of Moon") ==
      ["the director of Moon", "writer of Moon"], intent_mod._expand_nouns("the director and writer of Moon"))
check("_expand_nouns: no list", intent_mod._expand_nouns("who directed Moon") == ["who directed Moon"])
hit, others = intent_mod._films_of_with_others("films with Ian Holmes and Jonathan Pryce")
check("_films_of_with_others: two cast names", hit[:2] == ("cast member", "Ian Holmes")
      and others == [("cast member", "Jonathan Pryce")], (hit, others))
hit, others = intent_mod._films_of_with_others("movies directed by Terry Gilliam starring Jonathan Pryce")
check("_films_of_with_others: a second role after 'starring'", hit[:2] == ("director", "Terry Gilliam")
      and others == [("cast member", "Jonathan Pryce")], (hit, others))
hit, others = intent_mod._films_of_with_others("films Terry Gilliam directed with Jonathan Pryce")
check("_films_of_with_others: 'directed with Y'", hit[:2] == ("director", "Terry Gilliam")
      and others == [("cast member", "Jonathan Pryce")], (hit, others))

# --- linker: a real word is no typo of another word (H4) ---
check("'will smyth' does not fuzzy-match Willow Smyth", not [c for c in L.link("will smyth", want={"person"})
                                                              if c.label == "Willow Smyth"])
check("'kids' does not fuzzy-match GKIDS", not [c for c in L.link("kids", want={"company"}) if c.label == "GKIDS"])
check("a typo still links ('alfred hitchcok')", [c.label for c in L.link("alfred hitchcok", want={"person"})][:1]
      == ["Alfred Hitchcock"])
check("_other_word: grown word", L._other_word("will smyth", "willow smyth"))
check("_other_word: typo kept", not L._other_word("alfred hitchcok", "alfred hitchcock"))
check("_one_edit", _one_edit("hank", "hanks") and _one_edit("form", "from") and not _one_edit("will", "willow"))
check("_aligned", _aligned("tom hanx", "tom hanks") and not _aligned("tom hanx", "tim burton"))
check("NOT_MEMBER: a film 'inspired by' a series is no member of it",
      set(L.films_of_entity(e("SER1"))) == {str(e("F13")), str(e("F14"))}, L.films_of_entity(e("SER1")))
check("_kind_by_use: a classless production company", L.kind_of(e("U1")) == "company", L.kind_of(e("U1")))

# --- filmography ---
check("mask_names blanks a name", "animation" not in mask_names("Sunrise Animation Studios films", ["Sunrise Animation Studios"]))
check("mask_names folds accents", "amelie" not in mask_names("Amélie Story cast", ["Amelie Story"]))
ov = F.answer("How many Sunrise Animation Studios films are there?")
check("H2: a genre word inside a company name is no filter", ov is not None and len(ov.answer_uris) == 2
      and "animated" not in ov.text, ov and ov.text)
ov = F.answer("Sunrise Animation Studios animated films")
check("a genre word outside the name still filters", ov is not None and lab(ov.answer_uris) == {"Cowboy Tale"},
      ov and ov.text)
ov = F.answer("Sunrise Animation Studios films from 1998")
check("H1: 'from <year>' is that year in the filmography", ov is not None and lab(ov.answer_uris) == {"Cowboy Tale"},
      ov and ov.text)
check("TV series are not counted as films", ov is not None and "Sunrise Hour" not in ov.text)
ov = F.answer("Who played Sam Lowry?")
check("H3: performer link answers who played a character", ov is not None and "Jonathan Pryce" in ov.text
      and "Ian Holmes" not in ov.text and lab(ov.answer_uris) == {"Jonathan Pryce"}, ov and ov.text)
check("performers()", [labels[a] for a in F.performers(e("CH1"))] == ["Jonathan Pryce"])
ov = F.answer("who played Lonely Ghost")
check("no performer link: says the graph does not say", ov is not None and ov.text.startswith(
    "The graph does not say who plays Lonely Ghost"), ov and ov.text)
ov = F._character(L.link("Sam Lowry")[0], "Sam Lowry films")
check("_character without 'who played': the films", ov is not None and lab(ov.answer_uris) == {"Brazil"}, ov and ov.text)
ov = F.answer("hitchcok films")
check("surname typo links the known director", ov is not None and "Alfred Hitchcock" in ov.text, ov and ov.text)
check("_surname_typo needs an unknown word", F._surname_typo("hitchcok") and not F._surname_typo("brazil"))
check("_surname: a capitalized surname", [c.label for c in F._surname("films by Hitchcock", ("person",))] ==
      ["Alfred Hitchcock"])
ov = F.answer("What did Clint Westwood and Morgan Freedman do together?")
check("no role named: films that credit both in any role", ov is not None and lab(ov.answer_uris) ==
      {"Gold Plain", "Baby Fight"}, ov and ov.text)
people = F.entities("films Tim Barton made with Johnny Deep")
check("_person_roles: cue before each name", F._person_roles(people, "films Tim Barton directed with Johnny Deep "
                                                             "acting", None)[0] == "director")
ov = F.answer("films Tim Barton made with Johnny Deep", roles={"Tim Barton": "director", "Johnny Deep": "cast member"})
check("roles from the parser decide a shared answer", ov is not None and lab(ov.answer_uris) ==
      {"Sleepy Town", "Big Fish Tale"}, ov and ov.text)
check("_roles_by_name matches by name words", F._roles_by_name(people, [None, None],
                                                               {"Deep": "cast member"}).count("cast member") == 1)
ov = F.missing("what did will smyth star in", names=["will smyth"])
check("missing(): a lower-case name from the parser", ov is not None and "will smyth" in ov.text, ov and ov.text)
check("missing(): a known name is not missing", F.missing("x", names=["Terry Gilliam"]) is None)
check("_in_name_run: 'Will' inside a sentence is a first name", _in_name_run("What did Will Smyth star in", "smyth"))
check("_in_name_run: a question word at the start is not", not _in_name_run("Hitchcock films", "hitchcock"))
check("_in_name_run: Title Case question words do not count", not _in_name_run("Movies With Hitchcock", "hitchcock"))
check("_inside_longer: 'Lowry' sits in the character 'Sam Lowry'", F._inside_longer(["lowry"], ["sam", "lowry"]))
cand = L.link("Danny Elfmann", want={"person"})[0]
check("_namesake_with_role keeps a person credited in the role",
      F._namesake_with_role(cand, "composer").uri == cand.uri)

# --- recommender wording ---
check("M9: a name with 'Love' is no similarity cue", not rec.has_similarity_cue("Linda Lovelace movies")
      and not rec.has_similarity_cue("Lovecraft stories"))
check("similarity cue still on 'I loved'", rec.has_similarity_cue("I loved Brazil"))
for q in ["fun movies if you liked Brazil", "good films for anyone who enjoyed Moon"]:
    check(f"recommendation: {q!r}", rec.is_recommendation_question(q))
check("'if you liked X' seed", rec.extract_movie_titles("fun movies if you liked Brazil") == ["Brazil"],
      rec.extract_movie_titles("fun movies if you liked Brazil"))
for q in ["anything creepy this evening", "I want something sad", "what's a great western for the weekend",
          "can you name a good comedy", "family movies"]:
    check(f"seedless request routes to recommendations: {q!r}", rec.is_recommendation_question(q))
check("is_theme_request: a mood with no film noun", rec.is_theme_request("something funny to watch"))
check("is_theme_request: a person is not a theme", not rec.is_theme_request("Terry Gilliam movies"))
gil = L.link("Terry Gilliam", want={"person"})[0]
seeds, films = rec._taste_films(g, L, gil)
check("_taste_films: a filmmaker's films", lab(films) == {"Brazil"}, films)
get_linker(g, labels)
with contextlib.redirect_stdout(io.StringIO()):
    recs = rec.recommend_movies(g, ["Max Road One"], top_k=5, candidate_filter=lambda u: str(u) == str(e("F14")))
check("candidate_filter: only allowed films are ranked", all(t == "Max Road Two" for t, _ in recs), recs)

# --- responder on the synthetic graph ---
a, m = ask("How many Sunrise Animation Studios films are there?")
check("count of a company with a genre word in its name", "2 films" in a and "animated" not in a, a)
a, m = ask("What did Aardvark make?")
check("a company found by kind gets production company", "Clay Days" in a and m["relation"] == "production company", a)
a, m = ask("What has Aardvark released?")
check("'released' by a company: its films", "Clay Days" in a, a)
a, m = ask("Who played Sam Lowry?")
check("who played a character: the performer", "Jonathan Pryce" in a and "Ian Holmes" not in a, a)
a, m = ask("which characters appear in Paprika?")
check("characters relation", "Detective Konakawa" in a and m["relation"] == "characters", a)
a, m = ask("where is Paprika from")
check("where is X from: country of origin", "Japan" in a, a)
a, m = ask("was Moon nominated for anything")
check("nominated for anything: the film's nominations", "Hugo Award" in a, a)
a, m = ask("brazil screenplay by")
check("trailing 'by': the screenwriter", "Tom Stoppard" in a, a)
a, m = ask("Who directed Brazil and who composed the music?")
check("multi part with 'the music'", "Terry Gilliam" in a and "Michael Kamen" in a, a)
a, m = ask("brazil - director and composer?")
check("title - noun and noun", "Terry Gilliam" in a and "Michael Kamen" in a, a)
a, m = ask("films Tim Barton made with Johnny Deep")
check("shared: director with his actor", "Sleepy Town" in a and "Big Fish Tale" in a and "Pirate Bay" not in a, a)
a, m = ask("which films did Danny Elfmann score for Tim Barton")
check("shared: composer for a director", "Sleepy Town" in a and "Red Sky" not in a and "Pirate Bay" not in a, a)
a, m = ask("What did Clint Westwood and Morgan Freedman do together?")
check("shared: any role", "Gold Plain" in a and "Baby Fight" in a, a)
a, m = ask("What movies did Will Smyth star in?")
check("missing name, not a namesake", "no entity named Will Smyth" in a and "Willow" not in a, a)
a, m = ask("will smyth movies")
check("missing lower-case name", "no entity named will smyth" in a.lower() and "Willow" not in a, a)
a, m = ask("kids movies")
check("'kids movies' is a themed request, not GKIDS", m["route"] == "recommendation" and "GKIDS" not in a, (m["route"], a))
a, m = ask("Who directed the Max Road movies?")
check("series: no director of an 'inspired by' film", "George Millar" in a and "Kevin Reynold" not in a, a)
a, m = ask("Terry Gilliam films from 1985")
check("filmography year 'from 1985' keeps its phrase", "from 1985" in a and "since" not in a, a)

# --- responder helpers ---
it = parse_intent("How many Sunrise Animation Studios films are there?")
it.count, it.kind = False, "films_of"
check("_has_filters ignores a genre word in the subject's name",
      not Responser._has_filters(it, "Sunrise Animation Studios films"))
it = parse_intent("Sunrise Animation Studios films")
check("_has_filters sees a genre outside the name", Responser._has_filters(it, "Sunrise Animation Studios horror films"))
cand = L.link("Brazil", want={"film"})[0]
linked = {"kind": "film", "entity_uri": cand.uri, "alternatives": [], "cand": cand, "relation": "producer",
          "property_uri": P + "P162", "inverse": False, "via_films": []}
r = Responser()
r.last_meta = {"answer_uris": [str(e("Q404"))], "entity_uri": cand.uri}
check("_old_answer_ok: bare Q-IDs are no answer", not r._old_answer_ok(None, labels))
r.last_meta = {"answer_uris": [str(e("D1"))], "entity_uri": str(e("F3"))}
check("_old_answer_ok: another film than the linked one", not r._old_answer_ok(linked, labels))
r.last_meta = {"answer_uris": [str(e("D1"))], "entity_uri": cand.uri}
check("_old_answer_ok: same film, named value", r._old_answer_ok(linked, labels))
r.last_meta = {}
check("_film_gap: says what is missing", r._film_gap(None, linked, g, labels) == "The graph has no producer for Brazil (1985).",
      r._film_gap(None, linked, g, labels))
check("_embedding_guess: none without embeddings", r._embedding_guess(g, labels, cand.uri, p("P57")) is None)
E = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 0.1]])
emb = Responser(E, np.array([[1.0, 0.0]]), {str(e("F1")): 0, str(e("F3")): 1, str(e("D1")): 2},
                {P + "P57": 0}, {0: str(e("F1")), 1: str(e("F3")), 2: str(e("D1"))})
with contextlib.redirect_stdout(io.StringIO()):
    guess = emb._embedding_guess(g, labels, str(e("F1")), p("P57"))
check("_embedding_guess: skips a film, takes a real director", guess == (str(e("D1")), "Terry Gilliam"), guess)

# --- pictures ---
check("'got a photo of X?' is a picture request", is_multimedia_query("got a photo of Ava Doe?"))
check("'any pics of X' is a picture request", is_multimedia_query("any pics of Ava Doe"))
check("a plain question is not", not is_multimedia_query("what did Ava Doe star in"))
with contextlib.redirect_stdout(io.StringIO()):
    img, err = responser._resolve_image_url("pic of Ava Doe pls", g, {}, linker=L)
check("chat trailer 'pls' is no part of the name", img == "image:pf/ava", (img, err))
with contextlib.redirect_stdout(io.StringIO()):
    img, err = responser._resolve_image_url("got a photo of Ava Doe?", g, {}, linker=L)
check("'got a photo of X?' finds the person", img == "image:pf/ava", (img, err))
check("_with_image: exact name with a picture", responser._with_image(g, L, "Ava Doe", {"person"}, "profile") == e("AV"))
check("_with_image: no picture, no match", responser._with_image(g, L, "Terry Gilliam", {"person"}, "profile") is None)

# --- server summary and old-path entity resolution ---
check("_COUNT_HEAD keeps the count sentence",
      _summarize_list("Brazil has 3 awards in the graph. Brazil won A and B and C.", "factual", 5)
      == "Brazil has 3 awards in the graph.")
check("_COUNT_HEAD leaves a multi-part answer whole",
      _summarize_list("Brazil has 3 awards in the graph. X.", "factual", 5, n_parts=2).endswith("X."))
check("resolve_entity: a word in no label gives nothing", resolve_entity(g, {}, "Brazil Zzyzx") == [])
check("resolve_entity: accents folded", resolve_entity(g, {}, "amelie story") == [e("F27")],
      resolve_entity(g, {}, "amelie story"))
check("resolve_entity: a label part", e("F22") in resolve_entity(g, {}, "good will"))

print(f"\n{passed}/{passed + failed} passed")
sys.exit(1 if failed else 0)
