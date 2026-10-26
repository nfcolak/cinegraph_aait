# intent.py
# Deterministic intent parser: question text -> Intent (kind, relation, subject mention,
# year hint, genre filter, sub-questions). Pure text: no graph, no rdflib, no I/O.

import re
from dataclasses import dataclass, field
from typing import List, Optional

RELATIONS = [  # canonical labels, the keys of core.relation.FALLBACK_PRED_URIS
    "director", "cast member", "screenwriter", "composer", "producer", "production company",
    "distributed by", "cinematographer", "nominated for", "award received", "genre",
    "country of origin", "original language", "publication date",
]

# Confidence bands (design.md 1.1); >= USE_THRESHOLD means "use me".
CONF_HIGH = 0.9   # relation phrase and a usable mention
CONF_WEAK = 0.6   # weak relation cue only, or a mention of 3 letters or fewer
CONF_LOW = 0.3    # mention empty or too long
CONF_NONE = 0.0   # kind "unknown"
USE_THRESHOLD = 0.5
MAX_MENTION_WORDS = 12
SHORT_MENTION_LETTERS = 3
YEAR_MIN, YEAR_MAX = 1880, 2030


@dataclass
class Intent:
    kind: str                      # "fact" (film -> value), "films_of" (person/company -> films), "unknown"
    relation: Optional[str]        # one of RELATIONS, or None
    mention: Optional[str]         # subject text as typed (case kept), no relation words, no wh-words
    quoted: bool = False           # mention came from quotes
    year: Optional[int] = None     # "Titanic (1997)", "the 1997 Titanic", "Titanic from 1997"
    genre: Optional[str] = None    # films_of only: key of the genre table in core/responser.py
    confidence: float = 0.0        # 0..1; >= 0.5 means "use me"
    parts: List["Intent"] = field(default_factory=list)  # further sub-questions; "it" -> same mention

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "relation": self.relation,
            "mention": self.mention,
            "quoted": self.quoted,
            "year": self.year,
            "genre": self.genre,
            "confidence": self.confidence,
            "parts": [p.to_dict() for p in self.parts],
        }


# --- relation lexicon ------------------------------------------------------------------
# relation -> regex fragments (case-insensitive, whole words). Fragments in WEAK_FRAGMENTS
# are weak cues: they only count when no strong fragment of any relation is present.
# A trailing _OF lets a noun cue swallow its preposition ("director of", "music for").

_OF = r"(?:\s+(?:of|for|from|to|in|on))?"

_W_MUSIC = r"(?:the\s+)?(?:original\s+)?music" + _OF
_W_WHEN = r"when"
_W_WHAT_YEAR = r"(?:in\s+)?(?:what|which)\s+year"

RELATION_LEXICON = {
    "director": [
        r"(?:the\s+)?directors?" + _OF,
        r"directed\s+by",
        r"direct(?:ed|ing|s)",
        r"(?:the\s+)?film\s?makers?" + _OF,
        r"helmed(?:\s+by)?",
        r"who\s+made",
        r"made\s+by",
        r"behind\s+the\s+camera(?:\s+(?:of|for|on|in))?",
    ],
    "cast member": [
        r"(?:the\s+)?(?:cast(?:\s+members?)?|actors?|actresses|actress|performers?)" + _OF,
        r"(?:who\s+)?(?:starred|acted|appeared|played|performed)\s+in",
        r"starr(?:ed|ing)",
        r"stars?\s+in",
        r"who(?:'s|\s+is|\s+was|\s+are|\s+were)\s+in",
    ],
    "screenwriter": [
        r"(?:the\s+)?(?:screen|script)?writers?" + _OF,
        r"wrote",
        r"writes",
        r"written(?:\s+by)?",
        r"(?:the\s+)?screenplay" + _OF,
        r"(?:the\s+)?scripts?" + _OF,
        r"(?:the\s+)?scenarists?" + _OF,
    ],
    "composer": [
        r"(?:the\s+)?composers?" + _OF,
        r"compos(?:ed|es|ing|e)(?:\s+by)?",
        r"scor(?:ed|es|ing)(?:\s+by)?",
        r"(?:the\s+)?(?:musical\s+)?score" + _OF,
        r"(?:the\s+)?(?:original\s+)?soundtracks?" + _OF,
        _W_MUSIC,
    ],
    "producer": [
        r"(?:the\s+)?(?:executive\s+)?producers?" + _OF,
        r"produc(?:ed|es|ing)(?:\s+by)?",
    ],
    "production company": [
        r"(?:the\s+)?production\s+compan(?:y|ies)" + _OF,
        r"(?:the\s+)?(?:film\s+|movie\s+)?(?:compan(?:y|ies)|studios?)(?:\s+(?:that|which|who))?"
        r"(?:\s+(?:produced|made|backed|financed))?" + _OF,
    ],
    "distributed by": [
        r"distribut(?:ed|es|ing)(?:\s+by)?",
        r"(?:the\s+)?(?:distribution\s+compan(?:y|ies)|distributors?)" + _OF,
    ],
    "cinematographer": [
        r"(?:the\s+)?cinematograph(?:ers?|y)" + _OF,
        r"(?:the\s+)?director\s+of\s+photography" + _OF,
        r"(?-i:\bDP\b)",
        r"(?:who\s+)?shot(?:\s+by)?",
        r"(?:who\s+filmed|filmed\s+by)",
    ],
    "nominated for": [
        r"nominat(?:ed|ions?|es?|ees?)(?:\s+for)?",
    ],
    "award received": [
        r"(?:the\s+)?(?:academy\s+awards?|awards?|oscars?|prizes?)" + _OF,
    ],
    "genre": [
        r"(?:the\s+)?genres?" + _OF,
        r"(?:what|which)\s+(?:kind|type|sort)\s+of\s+(?:film|movie)",
        r"(?:kind|type|sort)\s+of\s+(?:film|movie)",
    ],
    "country of origin": [
        r"(?:the\s+)?countr(?:y|ies)(?:\s+of\s+origin)?" + _OF,
        r"from\s+(?:what|which)\s+country",
    ],
    "original language": [
        r"(?:the\s+)?(?:original\s+)?languages?" + _OF,
    ],
    "publication date": [
        r"(?:the\s+)?release\s+(?:date|year)" + _OF,
        r"(?:the\s+)?(?:date|year)\s+of\s+(?:release|publication)(?:\s+of)?",
        r"(?:the\s+)?publication\s+date" + _OF,
        r"released?",
        r"(?:came|come|comes|coming)\s+out",
        r"premier(?:e|ed|es)",
        _W_WHAT_YEAR,
        _W_WHEN,
    ],
}
WEAK_FRAGMENTS = {_W_MUSIC, _W_WHEN, _W_WHAT_YEAR}

# winner -> losers: when both match, the loser's cue is dropped from the text
_OVERRIDES = [
    ("nominated for", "award received"),
    ("cinematographer", "director"),
    ("distributed by", "production company"),
    ("distributed by", "producer"),
    ("production company", "producer"),
]

# "wrote the soundtrack of X" / "made the music for X" mean composer
_MUSIC_OBJECT = re.compile(
    r"^\s+(?:the|a|an|original)\s+(?:original\s+)?(?:music|soundtrack|score|theme(?:\s+(?:music|song))?)"
    r"\s+(?:of|for|from|to|in|on)\b", re.I)
_MUSIC_OVERRIDABLE = {"screenwriter", "director", "producer"}

# a noun cue repeated right after the chosen cue ("who is in the cast of X") is absorbed
_ABSORB_EXTRA = {"cast member": re.compile(r"^(?:were|was|are|is)\s+in\b", re.I)}
_ENDS_WITH_PREP = re.compile(r"\b(?:of|for|from|to|in|on|by)$", re.I)
_ABSORB_SKIP = re.compile(r"^(?:who|that|which|being)\s+", re.I)

_COMPILED = {
    rel: [(re.compile(r"(?<!\w)(?:" + frag + r")(?!\w)", re.I), frag in WEAK_FRAGMENTS) for frag in frags]
    for rel, frags in RELATION_LEXICON.items()
}

# relations whose cue is followed by a question aux ("what genre is X", "when was X released")
_AUX_AFTER = {"genre", "publication date", "country of origin", "original language",
              "award received", "nominated for"}
_AUX_LEAD = re.compile(r"^(?:is|are|was|were|did|does|do|has|have|had)\s+", re.I)

# words that trail the subject for some relations ("X released", "X from", "X win")
_TRAIL = {
    "publication date": re.compile(
        r"(?:\s+(?:was|were|did|is|got|had|has))?\s+(?:released?|(?:came|come|comes)\s+out|premier(?:e|ed))"
        r"(?:\s+(?:in|on))?$"),
    "country of origin": re.compile(r"(?:\s+(?:originally|actually))?\s+(?:from|in|of)$"),
    "original language": re.compile(r"(?:\s+(?:spoken|made|filmed|shot|produced|released|dubbed))?\s+(?:in|from)$"),
    "genre": re.compile(r"(?:\s+(?:belong|fall|fit|count))?\s+(?:to|under|into|as)$"),
    "award received": re.compile(r"\s+(?:win|won|receive|received|get|got)$"),
    "nominated for": re.compile(r"\s+(?:get|got|receive|received)$"),
}

# --- text helpers ----------------------------------------------------------------------

_QUOTE_RX = re.compile(
    r'"([^"]+)"|“([^”]+)”|«([^»]+)»'
    r"|(?:^|(?<=[\s(]))['‘](.+?)['’](?=$|[\s?.!,;:)])")

_NOT_FACTUAL = re.compile(
    r"\b(?:recommend(?:ation)?s?|suggest(?:ion)?s?|similar\s+(?:to|movies?|films?)"
    r"|(?:movies?|films?)\s+like|something\s+like)\b", re.I)

_POLITE = re.compile(
    r"^(?:(?:hey|hi|hello|ok|okay|so|and|also|but|well|um|please)[,!.\s]+"
    r"|(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?(?:tell|show|give|let)\s+me\s+(?:know\s+)?"
    r"|(?:can|could|would|will)\s+you\s+(?:please\s+)?"
    r"|do\s+you\s+(?:know|remember|happen\s+to\s+know)\s+"
    r"|i\s+(?:want|need|wanna|would\s+like|'d\s+like|’d\s+like)\s+to\s+(?:know|find\s+out)\s+"
    r"|(?:name|list)\s+"
    r"|find\s+(?:out\s+)?)", re.I)

_SPLIT = re.compile(
    r"(?<=[?!])\s+(?=\w)"
    r"|\s*,?\s+and\s+(?=(?:who|whom|what|when|where|which|how|whose|is|was|were|are|did|does|do|has|have|tell|also)\b"
    r"|(?:directed|wrote|written|composed|scored|starred|stars|produced|released|shot|distributed)\b)", re.I)

_WH_LEAD = re.compile(
    r"^(?:who|whom|whose|what|which|when|where|how|is|are|was|were|did|does|do|has|have|had|also|and|then|so|ok)\b[\s,]*",
    re.I)
_AUX_TRAIL = re.compile(r"\s+(?:is|was|are|were|did|does|do|has|have|had|being|been)$", re.I)
_POLITE_TRAIL = re.compile(r"[\s,]+(?:please|thanks|thank\s+you|again|too)$", re.I)
_FILM_CALLED = re.compile(r"^(?:the\s+)?(?:movie|film|picture)\s+(?:called|named|titled|entitled)\s+", re.I)
_FILM_LEAD_THE = re.compile(r"^the\s+(?:movie|film|picture)\s+(?=\S)", re.I)
_FILM_LEAD_BARE = re.compile(r"^(?:movie|film|picture)\s+(?=\S)")  # lower case only: "Film Socialisme" stays
_FILM_ONLY = re.compile(r"^(?:the\s+)?(?:movie|film|picture|one)s?$", re.I)
_FILM_PLURAL_TAIL = re.compile(r"^(?:the\s+)?(?P<t>.*?\S)\s+(?:movies|films)$", re.I)
_FILM_SINGULAR_TAIL = re.compile(r"^(?P<t>.*?\S)\s+(?:movie|film)$", re.I)
_ARTICLE_ONLY = re.compile(r"^(?:the|a|an)$", re.I)
_POSSESSIVE = re.compile(r"['’]s?$")
_PRONOUN = re.compile(
    r"^(?:it|its|it['’]s|this|that|them|these|those|(?:that|this|the|the same)\s+(?:film|movie|one)|the\s+one)$",
    re.I)

_YEAR_PAREN = re.compile(r"\s*\((\d{4})\)")
_YEAR_THE = re.compile(r"\b[Tt]he\s+(\d{4})\s+(?=\S)")
_YEAR_TRAIL = re.compile(r"\s+(?:from|in|of)\s+(\d{4})$")
_YEAR_BARE = re.compile(r"^(?P<t>.*\S)\s+(?P<y>\d{4})$")

_PLACEHOLDER = re.compile(r"qtq(\d+)qtq")


def _valid_year(s: str) -> Optional[int]:
    y = int(s)
    return y if YEAR_MIN <= y <= YEAR_MAX else None


def _protect_quotes(text: str):
    """Replace quoted spans by placeholders so their words never act as relation cues."""
    quotes: List[str] = []

    def sub(m):
        quotes.append(next(g for g in m.groups() if g is not None))
        return f"qtq{len(quotes) - 1}qtq"

    return _QUOTE_RX.sub(sub, text), quotes


def _trim(s: str) -> str:
    return re.sub(r"[\s?!.,;:]+$", "", re.sub(r"\s+", " ", s).strip())


def _lead_strip(s: str) -> str:
    while True:
        t = _POLITE.sub("", s, count=1)
        if t == s:
            return s
        s = t


def _take_year(seg: str):
    """Move a year hint out of the segment: '(1997)', 'the 1997 X', trailing 'from 1997'."""
    year = None
    m = _YEAR_PAREN.search(seg)
    if m and _valid_year(m.group(1)):
        year = _valid_year(m.group(1))
        seg = seg[:m.start()] + seg[m.end():]
    else:
        m = _YEAR_THE.search(seg)
        if m and _valid_year(m.group(1)):
            year = _valid_year(m.group(1))
            seg = seg[:m.start()] + seg[m.end():]
        else:
            m = _YEAR_TRAIL.search(seg)
            if m and _valid_year(m.group(1)):
                year = _valid_year(m.group(1))
                seg = seg[:m.start()]
    return _trim(seg), year


# --- genres ----------------------------------------------------------------------------

_GENRE_MAP = {
    "biographical": "biographical", "biography": "biography", "action": "action",
    "comedy": "comedy", "comedies": "comedy", "drama": "drama", "dramas": "drama",
    "horror": "horror", "thriller": "thriller", "thrillers": "thriller",
    "romance": "romance", "romantic": "romantic", "sci-fi": "sci-fi", "scifi": "sci-fi",
    "fantasy": "fantasy", "documentary": "documentary", "documentaries": "documentary",
    "animated": "animated", "animation": "animated", "musical": "musical", "musicals": "musical",
    "western": "western", "westerns": "western", "crime": "crime", "mystery": "mystery",
}


def _genre_of(word: Optional[str]) -> Optional[str]:
    return _GENRE_MAP.get(word.lower()) if word else None


# --- films_of forms --------------------------------------------------------------------

_F = r"(?:movies?|films?)"
_PRE = r"(?:in\s+)?(?:(?:which|what)\s+)?(?:(?P<g>[\w\-]+)\s+)?"
_VERB = (r"(?:direct(?:ed)?|writ(?:e|ten)|wrote|compos(?:e|ed)|scor(?:e|ed)|produc(?:e|ed)|shoot|shot"
         r"|film(?:ed)?|star(?:red)?|act(?:ed)?|appear(?:ed)?|play(?:ed)?|featur(?:e|ed)|distribut(?:e|ed))")
_TAIL = r"(?:\s+(?:in|on|for))?(?:\s+(?:the\s+)?(?:music|soundtrack|score)(?:\s+for)?)?"
_VERB_REL = [
    ("direct", "director"), ("writ", "screenwriter"), ("wrote", "screenwriter"),
    ("compos", "composer"), ("scor", "composer"), ("produc", "producer"),
    ("shoot", "cinematographer"), ("shot", "cinematographer"), ("film", "cinematographer"),
    ("star", "cast member"), ("act", "cast member"), ("appear", "cast member"),
    ("play", "cast member"), ("featur", "cast member"), ("distribut", "distributed by"),
]
_COMPANY_HINT = re.compile(
    r"\b(?:pictures|studios?|entertainment|productions?|bros\.?|brothers|company|corporation|corp\.?|inc\.?|ltd\.?"
    r"|animation|disney|pixar|dreamworks|warner|universal|paramount|miramax|lionsgate|mgm|a24|columbia)\b", re.I)

# (regex, fixed relation or None to read it from group v)
_FILMS_OF = [
    (re.compile(rf"^{_PRE}{_F}\s+(?:did|does|do|has|have)\s+(?P<m>.+?)\s+(?P<v>{_VERB}){_TAIL}$", re.I), None),
    (re.compile(rf"^what\s+(?:{_F}\s+)?(?:did|does|has|have)\s+(?P<m>.+?)\s+(?P<v>{_VERB}){_TAIL}$", re.I), None),
    (re.compile(rf"^{_PRE}{_F}\s+(?:(?:is|are|was|were|has\s+been|have\s+been)\s+)?"
                rf"(?P<v>directed|written|composed|scored|produced|shot|filmed|distributed)\s+by\s+(?P<m>.+)$", re.I), None),
    (re.compile(rf"^{_PRE}{_F}\s+by\s+(?P<m>.+)$", re.I), "director"),
    (re.compile(rf"^{_PRE}{_F}\s+(?:with|starring|featuring)\s+(?P<m>.+)$", re.I), "cast member"),
    (re.compile(rf"^(?:which|what)\s+(?:(?P<g>[\w\-]+)\s+)?{_F}\s+(?:star|stars|feature|features)\s+(?P<m>.+)$", re.I),
     "cast member"),
    (re.compile(rf"^(?P<m>.+?)['’]s?\s+(?:(?P<g>[\w\-]+)\s+)?(?:{_F}|filmography)$", re.I), "director"),
    (re.compile(r"^(?:the\s+)?filmography\s+of\s+(?P<m>.+)$", re.I), "director"),
    (re.compile(r"^(?P<m>.+?)\s+filmography$", re.I), "director"),
]


def _relation_of_verb(verb: str) -> Optional[str]:
    v = verb.lower()
    for stem, rel in _VERB_REL:
        if v.startswith(stem):
            return rel
    return None


def _parse_films_of(seg: str):
    for rx, fixed in _FILMS_OF:
        m = rx.match(seg)
        if not m:
            continue
        gd = m.groupdict()
        rel = fixed or _relation_of_verb(gd["v"])
        if rel is None:
            continue
        mention = gd["m"]
        if rel == "producer" and _COMPANY_HINT.search(mention):
            rel = "production company"
        return rel, mention, _genre_of(gd.get("g")), False
    return None


# --- fact forms ------------------------------------------------------------------------

def _parse_fact(seg: str):
    cands = {}
    for rel, frags in _COMPILED.items():
        best = None
        strong = False
        for rx, weak in frags:
            m = rx.search(seg)
            if not m:
                continue
            if not weak:
                strong = True
            if best is None or (m.start(), -m.end()) < (best.start(), -best.end()):
                best = m
        if best is not None:
            cands[rel] = (best, strong)
    if not cands:
        return None
    for win, lose in _OVERRIDES:
        if win in cands and lose in cands:
            m_lose = cands[lose][0]
            m_win = cands[win][0]
            if m_lose.end() <= m_win.start() or m_lose.start() >= m_win.end():
                seg = seg[:m_lose.start()] + " " * (m_lose.end() - m_lose.start()) + seg[m_lose.end():]
            del cands[lose]
    rel = min(cands, key=lambda r: (not cands[r][1], cands[r][0].start(), -len(cands[r][0].group(0))))
    m, strong = cands[rel]
    post = seg[m.end():]
    if rel in _MUSIC_OVERRIDABLE and _MUSIC_OBJECT.match(post):
        rel = "composer"
    pre = seg[:m.start()]
    post = _absorb(rel, post)
    if rel in _AUX_AFTER:
        post = _AUX_LEAD.sub("", post.lstrip(), count=1)
    mention = _tidy(post)
    if not mention:
        mention = _clean_pre(pre)
    return rel, mention, None, not strong, _TRAIL.get(rel)


def _absorb(rel: str, post: str) -> str:
    """Drop a noun cue repeated right after the chosen cue ('who is in [the cast of] X')."""
    for _ in range(2):
        s = _ABSORB_SKIP.sub("", post.lstrip(), count=1)
        hit = None
        extra = _ABSORB_EXTRA.get(rel)
        if extra is not None:
            hit = extra.match(s)
        if hit is None:
            for rx, _weak in _COMPILED[rel]:
                m = rx.match(s)
                if m and _ENDS_WITH_PREP.search(m.group(0)) and (hit is None or m.end() > hit.end()):
                    hit = m
        if hit is None or not s[hit.end():].strip():
            break
        post = s[hit.end():]
    return post


def _tidy(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"^[\s,;:\-–]+|[\s?!.,;:\-–]+$", "", s)


def _clean_pre(pre: str) -> str:
    """Subject written before the cue ('Heat director', 'What is Alien's genre')."""
    s = _tidy(pre)
    while True:
        t = _WH_LEAD.sub("", s, count=1)
        if t == s:
            break
        s = t
    s = _AUX_TRAIL.sub("", s)
    if _ARTICLE_ONLY.match(s.strip()):
        return ""
    return _tidy(s)


# --- mention finishing -----------------------------------------------------------------

def _finish_mention(m: str, relation: str, trail, fact: bool):
    """Strip film words, possessive 's, trailing verbs. Returns (mention, series_form)."""
    m = _tidy(m)
    if fact:
        if trail is not None:
            m = _tidy(trail.sub("", m))
        m = _tidy(_POLITE_TRAIL.sub("", m))
        m = _FILM_CALLED.sub("", m)
        m = _FILM_LEAD_THE.sub("", m)
        m = _FILM_LEAD_BARE.sub("", m)
        if _FILM_ONLY.match(m):
            return ""
        t = _FILM_PLURAL_TAIL.match(m)
        if t and not _ARTICLE_ONLY.match(t.group("t")):
            m = t.group("t")                      # "the Batman movies" -> "Batman"
        else:
            t = _FILM_SINGULAR_TAIL.match(m)
            if t and not _ARTICLE_ONLY.match(t.group("t")):
                m = t.group("t")
    else:
        while True:
            t = _WH_LEAD.sub("", m, count=1)
            if t == m:
                break
            m = t
        m = _tidy(_POLITE_TRAIL.sub("", m))
    m = _POSSESSIVE.sub("", m)
    return _tidy(m)


def _confidence(relation: Optional[str], mention: Optional[str], weak: bool) -> float:
    if relation is None:
        return CONF_NONE
    if not mention or len(mention.split()) > MAX_MENTION_WORDS:
        return CONF_LOW
    letters = re.sub(r"\W", "", mention)
    if weak or (len(mention.split()) == 1 and len(letters) <= SHORT_MENTION_LETTERS):
        return CONF_WEAK
    return CONF_HIGH


def _resolve(mention: str, quotes: List[str]):
    """Put quoted text back. Returns (mention or None, quoted, is_pronoun)."""
    quoted = bool(_PLACEHOLDER.search(mention))
    if quoted:
        mention = _PLACEHOLDER.sub(lambda m: quotes[int(m.group(1))], mention)
        return (mention.strip() or None), True, False
    if not mention:
        return None, False, True
    if _PRONOUN.match(mention):
        return None, False, True
    return mention, False, False


@dataclass
class _Seg:
    kind: str
    relation: str
    mention: Optional[str]
    quoted: bool
    year: Optional[int]
    genre: Optional[str]
    weak: bool
    inherits: bool


def _parse_segment(seg: str, quotes: List[str]) -> Optional[_Seg]:
    seg = _lead_strip(_trim(seg))
    seg, year = _take_year(seg)
    hit = _parse_films_of(seg)
    if hit is not None:
        rel, mention, genre, weak = hit
        kind, trail = "films_of", None
    else:
        fact = _parse_fact(seg)
        if fact is None:
            return None
        rel, mention, genre, weak, trail = fact
        kind = "fact"
    mention = _finish_mention(mention, rel, trail, fact=(kind == "fact"))
    if year is None and not _PLACEHOLDER.search(mention):
        m = _YEAR_BARE.match(mention)
        if m and _valid_year(m.group("y")) and not _ARTICLE_ONLY.match(m.group("t")):
            year = _valid_year(m.group("y"))
            mention = m.group("t")
    text, quoted, pron = _resolve(mention, quotes)
    return _Seg(kind, rel, text, quoted, year, genre, weak, inherits=pron)


def _unknown() -> Intent:
    return Intent(kind="unknown", relation=None, mention=None, confidence=CONF_NONE)


def parse_intent(question: str) -> Intent:
    text, quotes = _protect_quotes(question or "")
    text = re.sub(r"\s+", " ", text).strip()
    if not text or _NOT_FACTUAL.search(text):
        return _unknown()
    segs = []
    for piece in _SPLIT.split(text):
        if piece and piece.strip():
            s = _parse_segment(piece, quotes)
            if s is not None:
                segs.append(s)
    if not segs:
        return _unknown()
    top = segs[0]
    intents = []
    for i, s in enumerate(segs):
        mention, quoted, year = s.mention, s.quoted, s.year
        if i > 0 and mention is None and s.inherits:
            mention, quoted = top.mention, top.quoted
            year = year if year is not None else top.year
        intents.append(Intent(
            kind=s.kind, relation=s.relation, mention=mention, quoted=quoted, year=year, genre=s.genre,
            confidence=_confidence(s.relation, mention, s.weak)))
    result = intents[0]
    result.parts = intents[1:]
    return result
