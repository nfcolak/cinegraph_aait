# intent.py
# Deterministic intent parser: question text -> Intent (kind, relation, subject mention,
# year hint, genre filter, sub-questions). Pure text: no graph, no rdflib, no I/O.

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional

RELATIONS = [  # canonical labels, the keys of core.relation.FALLBACK_PRED_URIS
    "director", "cast member", "screenwriter", "composer", "producer", "production company",
    "distributed by", "cinematographer", "nominated for", "award received", "genre",
    "country of origin", "original language", "publication date", "characters",
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
    # "fact" (film -> value), "films_of" (person/company -> films), "count" (how many films of a
    # person/company/series: same fields as films_of), "shared" (films common to the mention and every
    # films_of part, each with its own relation), "unknown"
    kind: str
    relation: Optional[str]        # one of RELATIONS, or None
    mention: Optional[str]         # subject text as typed (case kept), no relation words, no wh-words
    quoted: bool = False           # mention came from quotes
    year: Optional[int] = None     # fact: "Titanic (1997)", "the 1997 Titanic", "Titanic from 1997"
    genre: Optional[str] = None    # films_of/count/shared: key of the genre table in core/responser.py
    confidence: float = 0.0        # 0..1; >= 0.5 means "use me"
    parts: List["Intent"] = field(default_factory=list)  # further sub-questions; "it" -> same mention
    count: bool = False            # "how many ...": the answer should give a number
    year_from: Optional[int] = None  # films_of/count/shared: release year range, inclusive
    year_to: Optional[int] = None

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
            "count": self.count,
            "year_from": self.year_from,
            "year_to": self.year_to,
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
        r"(?:who\s+)?(?:play(?:s|ed)|portray(?:s|ed)|voic(?:es|ed))",  # "who played Gandalf"
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
        r"where\s+(?:is|was|are|were|does|do|did)(?=\s.*\bfrom\W*$)",  # "where is Amélie from"
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
    "characters": [
        r"(?:the\s+)?(?:main\s+)?(?:fictional\s+)?characters?" + _OF,
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
    r"^\s+(?:(?:the|a|an|original)\s+(?:original\s+)?(?:music|soundtrack|score|theme(?:\s+(?:music|song))?)"
    r"\s+(?:of|for|from|to|in|on)\b"
    r"|(?:its|their)\s+(?:original\s+)?(?:music|soundtrack|score)\s*$)", re.I)
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
              "award received", "nominated for", "characters"}
_AUX_LEAD = re.compile(r"^(?:is|are|was|were|did|does|do|has|have|had)\s+", re.I)
# "which country produced X": a verb between the cue and the subject
_VERB_LEAD = {"country of origin": re.compile(r"^(?:made|produced|filmed|shot|created)\s+(?:in\s+)?", re.I),
              "characters": re.compile(r"^(?:(?:appear|appeared|appearing)\s+)?(?:in|of|from)\s+", re.I)}
# the object slot names no film ("nominated for anything", "screenplay by"): the subject stands before the cue
_EMPTY_OBJECT = re.compile(
    r"^(?:(?:any|anything|something|what|which|whatever)(?:\s+(?:awards?|prizes?|oscars?|nominations?|ones?|people))?"
    r"|by|of|for|from|to|in|on|with)$", re.I)

# words that trail the subject for some relations ("X released", "X from", "X win")
_TRAIL = {
    "publication date": re.compile(
        r"(?:\s+(?:was|were|did|is|got|had|has))?\s+(?:released?|(?:came|come|comes)\s+out|premier(?:e|ed))"
        r"(?:\s+(?:in|on))?$"),
    "country of origin": re.compile(
        r"(?:\s+(?:originally|actually|first))?(?:\s+(?:made|produced|filmed|shot|created|come|comes))?"
        r"\s+(?:from|in|of)$"),
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
    r"|(?:movies?|films?)\s+like|something\s+like|more\s+like|else\s+(?:is\s+)?like|in\s+the\s+style\s+of"
    r"|[\w'’]+-like\s+(?:movies?|films?)"
    r"|fans?\s+of|what\s+(?:should|could|can)\s+i\s+watch|what\s+to\s+watch|watch\s+next|what\s+next)\b", re.I)

_POLITE = re.compile(
    r"^(?:(?:hey|hi|hello|hiya|yo|ok|okay|so|and|also|but|well|um+|uh+|please|btw|lol|quick\s+question|question)"
    r"(?:\s+there)?(?:[,!.:;\s]+|$)"
    r"|(?:i\s+(?:was\s+)?wonder(?:ing)?|i['’]?m\s+(?:curious|wondering)|just\s+wondering|any\s+idea)[,:]?\s+"
    r"|(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?(?:tell|show|give|let)\s+me\s+(?:know\s+)?"
    r"|(?:can|could|would|will)\s+you\s+(?:please\s+)?"
    r"|do\s+you\s+(?:know|remember|happen\s+to\s+know)\s+"
    r"|i\s+(?:want|need|wanna|would\s+like|'d\s+like|’d\s+like)\s+to\s+(?:know|find\s+out)\s+"
    r"|(?:name|list)\s+"
    r"|find\s+(?:out\s+)?)", re.I)

# chatter after the question: "..., just curious", "... pls", "... thank you"
_CHAT_TRAIL = re.compile(
    r"[\s,;:\-–]+(?:please|pls|plz|(?:thanks|thank\s+you)(?:\s+(?:so|very)\s+much|\s+a\s+lot)?|thx|just\s+curious"
    r"|if\s+you\s+know"
    r"|if\s+you\s+can|lol|haha|btw|by\s+the\s+way|asap|real\s+quick|quickly|for\s+me)$", re.I)

# --- noise normalization (emoji, emoticons, repeated punctuation, chat spelling, relation-word typos) ---

_EMOTICON = re.compile(r"(?<!\w)(?:[:;=][\-']?[()DPpOo3/\\|\]\[*]+|<3+|xD+|XD+)(?!\w)")
_REPEAT_PUNCT = re.compile(r"([?!.,])[?!.,]+")
_CHAT_WORDS = {"u": "you", "ur": "your", "r": "are", "pls": "please", "plz": "please", "thx": "thanks",
               "wat": "what", "wht": "what", "whos": "who is", "whats": "what is", "abt": "about"}
# a chat word stands alone: "u-571" and "R. Kelly" keep their letter
_CHAT_RX = re.compile(r"(?<![\w'’\-])(?:" + "|".join(_CHAT_WORDS) + r")(?![\w'’.\-])")
# film words the relation lexicon does not hold as one word
_TYPO_EXTRA = ["screenwriter", "screenplay", "soundtrack", "soundtracks", "starring", "starred", "movies",
               "filmography", "cinematographer"]
_TYPO_SUFFIXES = ("", "s", "es", "ed", "d", "ing", "er", "ers", "or", "ors", "y", "ies", "ion", "ions", "e")
_TYPO_TARGET_MIN = 5


def _lexicon_words() -> List[str]:
    """Single words the relation lexicon accepts ('director', 'genre', 'nominations'): stems of its
    fragments plus common suffixes, kept when a fragment matches the whole word."""
    words = set()
    for frags in RELATION_LEXICON.values():
        whole = [re.compile(r"(?:" + f + r")", re.I) for f in frags]
        for frag in frags:
            for stem in re.findall(r"[a-z]{3,}", frag):
                for base in (stem, stem[:-1]):
                    for suf in _TYPO_SUFFIXES:
                        w = base + suf
                        if len(w) >= _TYPO_TARGET_MIN and w not in words and any(rx.fullmatch(w) for rx in whole):
                            words.add(w)
    return sorted(words | set(_TYPO_EXTRA), key=lambda w: (-len(w), w))


# relation and film words worth correcting; a token one edit away from one of them is replaced
_TYPO_TARGETS = _lexicon_words()
_TYPO_SET = set(_TYPO_TARGETS)
# real English words one edit away from a target (checked against a word list): never "corrected"
_TYPO_KEEP = {"waiter", "waiters", "nominee", "nominees", "scarred", "scarring", "distribute", "county",
              "compost", "compote", "coring", "dominate", "dominated", "domination", "factor", "helmet", "plated",
              "player", "premier", "scorned", "scoured", "scouring", "shored", "shoring", "snoring", "sparred",
              "sparring", "splayed", "staring", "starling", "starting", "starved", "stirring", "studious",
              "tarred", "whites", "voided", "britten"}
_TYPO_MIN_LEN = 6
_TOKEN = re.compile(r"[A-Za-z]+")
_typo_memo = {}


def _edit1(a: str, b: str) -> bool:
    """True when a and b differ by one insertion, deletion, substitution or adjacent swap."""
    la, lb = len(a), len(b)
    if abs(la - lb) > 1 or a == b:
        return False
    if la == lb:
        diff = [i for i in range(la) if a[i] != b[i]]
        if len(diff) == 1:
            return True
        return len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]
    if la > lb:
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


def _fix_typo(word: str) -> Optional[str]:
    low = word.lower()
    if low not in _typo_memo:
        hit = None
        plural_pair = low[:-1] in _TYPO_SET or low + "s" in _TYPO_SET  # "screenplays", "nomination"
        if len(low) >= _TYPO_MIN_LEN and low not in _TYPO_SET and low not in _TYPO_KEEP and not plural_pair:
            for t in _TYPO_TARGETS:
                if _edit1(low, t):
                    hit = t
                    break
        _typo_memo[low] = hit
    return _typo_memo[low]


def _denoise(text: str) -> str:
    if any(ord(ch) > 0x2000 for ch in text):
        text = "".join(" " if unicodedata.category(ch) in ("So", "Cs", "Co") or 0xFE00 <= ord(ch) <= 0xFE0F
                       or ord(ch) == 0x200D else ch for ch in text)
    text = _EMOTICON.sub(" ", text)
    text = _REPEAT_PUNCT.sub(r"\1", text)
    text = _CHAT_RX.sub(lambda m: _CHAT_WORDS[m.group(0)], text)
    shout = text.isupper()

    def fix(m):
        w = m.group(0)
        # lower-case words only (or a shouted question): a capitalized word may be part of a title
        if not (w.islower() or shout or m.start() == 0):
            return w
        t = _fix_typo(w)
        if t is None:
            return w
        return t.upper() if shout else t
    text = _TOKEN.sub(fix, text)
    return re.sub(r"\s+", " ", text).strip()

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
    r"^(?:it|its|it['’]s|this|that|them|these|those|(?:that|this|the|the same)\s+(?:film|movie|one)|the\s+one"
    r"|(?:its|their)\s+(?:original\s+)?(?:music|score|soundtrack|cast|director|screenplay|script|songs?))$",
    re.I)
# a later part about "the music" / "the cast" means the first part's film (lower case only: "The Score" is a title)
_THE_PART = re.compile(r"^the\s+(?:original\s+)?(?:music|score|soundtrack|cast|director|screenplay|script|songs?"
                       r"|film|movie|characters)$")
# title before the question: "pulp fiction who wrote it", "Heat - when did it come out"
_WH_TAIL = re.compile(r"(?:[\s,;:\-–]+|^)(?:who|whom|what|when|which|where|how)(?:\s+(?:is|was|are|were|did|does|do))?\s*$",
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


# --- year ranges and decades -------------------------------------------------------------

# optional verb before the range: "released after 2011", "that came out in the 90s"
_REL = (r"(?:(?:that|which)\s+)?(?:(?:were|was|are|is|got)\s+)?"
        r"(?:(?:released|made|filmed|shot|produced|out|(?:came|come|coming)\s+out)\s+)?")
_DECADE_WORDS = {"twenties": 1920, "thirties": 1930, "forties": 1940, "fifties": 1950, "sixties": 1960,
                 "seventies": 1970, "eighties": 1980, "nineties": 1990}
_YEAR_END = r"(?=$|[\s?!.,;:)])"
_DECADE = re.compile(
    rf"(?:^|[\s(]){_REL}(?:(?:from|in|of|during)\s+)?(?:the\s+)?(?:(?P<q>early|mid|late)[\s\-]+)?(?:the\s+)?"
    r"(?P<d>(?:1[89]|20)\d0['’]?s|['’]?\d0['’]?s|" + "|".join(_DECADE_WORDS) + r")" + _YEAR_END, re.I)
_BETWEEN = re.compile(
    rf"(?:^|\s){_REL}(?:(?:between|from)\s+)?(?P<a>\d{{4}})\s*(?:and|to|until|till|-|–)\s*(?P<b>\d{{4}})" + _YEAR_END,
    re.I)
_AFTER = re.compile(
    rf"(?:^|\s){_REL}(?P<w>after|since|post|later\s+than|newer\s+than)\s+(?:the\s+year\s+)?(?P<y>\d{{4}})"
    r"(?:\s+(?:onwards?|and\s+later|on))?" + _YEAR_END, re.I)
_ONWARDS = re.compile(rf"(?:^|\s){_REL}from\s+(?P<y>\d{{4}})\s+(?:onwards?|and\s+later|on)" + _YEAR_END, re.I)
_BEFORE = re.compile(
    rf"(?:^|\s){_REL}(?P<w>before|until|till|up\s+to|prior\s+to|pre|earlier\s+than|older\s+than)\s+(?:the\s+year\s+)?"
    r"(?P<y>\d{4})" + _YEAR_END, re.I)
# one year: "in 1994", "from 1994" (a year, not "since"), "of 1994"
_IN_YEAR = re.compile(rf"(?:^|\s){_REL}(?:in|of|during|from)\s+(?:the\s+year\s+)?(?P<y>\d{{4}})" + _YEAR_END, re.I)
_QUARTER = {"early": (0, 3), "mid": (4, 6), "late": (7, 9)}
_EXCLUSIVE = ("after", "post", "later than", "newer than", "before", "prior to", "pre", "earlier than", "older than")


def _decade_start(d: str) -> Optional[int]:
    d = d.lower().replace("'", "").replace("’", "")
    if d in _DECADE_WORDS:
        return _DECADE_WORDS[d]
    digits = d[:-1]
    if len(digits) == 4:
        return int(digits)
    tens = int(digits)  # "80s" -> 1980; "00s", "10s" -> 2000, 2010
    return 2000 + tens if tens < 20 else 1900 + tens


def _find_range(text: str, single: bool = False):
    """(match, first year, last year, phrase) of the release years the text names, or None.
    single: also a lone year ("in 1994", "from 1994"), which the parser leaves to _take_year."""
    m = _BETWEEN.search(text)
    if m and _valid_year(m.group("a")) and _valid_year(m.group("b")):
        lo, hi = sorted((int(m.group("a")), int(m.group("b"))))
        return m, lo, hi, f"from {lo} to {hi}"
    m = _DECADE.search(text)
    if m:
        start = _decade_start(m.group("d"))
        if m.group("q"):
            q = m.group("q").lower()
            a, b = _QUARTER[q]
            return m, start + a, start + b, f"from the {q} {start}s"
        return m, start, start + 9, f"from the {start}s"
    m = _ONWARDS.search(text)
    if m and _valid_year(m.group("y")):
        return m, int(m.group("y")), None, f"since {m.group('y')}"
    for rx, low_end in ((_AFTER, True), (_BEFORE, False)):
        m = rx.search(text)
        if m and _valid_year(m.group("y")):
            y = int(m.group("y"))
            w = re.sub(r"\s+", " ", m.group("w").lower())
            excl = w in _EXCLUSIVE
            if low_end:
                return m, y + excl, None, f"after {y}" if excl else f"since {y}"
            return m, None, y - excl, f"before {y}" if excl else f"until {y}"
    if single:
        m = _IN_YEAR.search(text)
        if m and _valid_year(m.group("y")):
            y = int(m.group("y"))
            return m, y, y, f"from {y}"
    return None


def year_span(text: str):
    """(first year, last year, phrase) of the release years a question names, or None. The one
    year-range reader of the agent: core/filmography.py and core/recommender.py use it too."""
    hit = _find_range(re.sub(r"\s+", " ", text or ""), single=True)
    return hit[1:] if hit else None


def _take_range(seg: str):
    """Move a release year range out of the segment. Returns (segment, year_from, year_to)."""
    hit = _find_range(seg)
    if hit is None:
        return seg, None, None
    m, lo, hi, _phrase = hit
    return _trim(seg[:m.start()] + " " + seg[m.end():]), lo, hi


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


# a plural genre noun used as the film noun: "Tom Hanks comedies" -> "Tom Hanks comedy films"
_GENRE_PLURAL = {"comedies": "comedy", "dramas": "drama", "thrillers": "thriller", "westerns": "western",
                 "musicals": "musical", "documentaries": "documentary", "romances": "romance"}
_GENRE_NOUN = re.compile(r"\b(?P<p>" + "|".join(_GENRE_PLURAL) + r")\b(?!\s+(?:movies?|films?)\b)", re.I)
_SCIFI = re.compile(r"\bscience[\s\-]+fiction\b", re.I)


def _genre_nouns(seg: str) -> str:
    seg = _SCIFI.sub("sci-fi", seg)
    return _GENRE_NOUN.sub(lambda m: _GENRE_PLURAL[m.group("p").lower()] + " films", seg)


# --- films_of forms --------------------------------------------------------------------

_F = r"(?:movies?|films?)"
_FS = r"(?:movies|films)"
_PRE = r"(?:in\s+)?(?:(?:which|what)\s+)?(?:all\s+(?:of\s+)?)?(?:(?P<g>[\w\-]+)\s+)?"
# genre word between a name and the film noun; "animation" is left out: it ends company names
_GEN = "(?:(?P<g>" + "|".join(re.escape(k) for k in sorted(_GENRE_MAP, key=len, reverse=True)
                              if k != "animation") + r")\s+)?"
_AUX = r"(?:(?:did|does|do|has|have|had)\s+)"
_VERB = (r"(?:direct(?:s|ed)?|writ(?:e|es|ten)|wrote|compos(?:e|es|ed)|scor(?:e|es|ed)|produc(?:e|es|ed)|shoot|shot"
         r"|film(?:ed)?|star(?:s|red)?|act(?:s|ed)?|appear(?:s|ed)?|play(?:s|ed)?|featur(?:e|es|ed)"
         r"|distribut(?:e|es|ed)|mak(?:e|es)|made|voic(?:e|ed)|releas(?:e|es|ed)|put\s+out)")
_TAIL = r"(?:\s+(?:in|on|for))?(?:\s+(?:the\s+)?(?:music|soundtrack|score)(?:\s+for)?)?"
_VERB_REL = [
    ("direct", "director"), ("writ", "screenwriter"), ("wrote", "screenwriter"),
    ("compos", "composer"), ("scor", "composer"), ("produc", "producer"),
    ("shoot", "cinematographer"), ("shot", "cinematographer"), ("film", "cinematographer"),
    ("star", "cast member"), ("act", "cast member"), ("appear", "cast member"),
    ("play", "cast member"), ("featur", "cast member"), ("voic", "cast member"),
    ("distribut", "distributed by"), ("mak", "director"), ("made", "director"), ("helm", "director"),
    ("releas", "director"), ("put", "director"),
]
# company words in a name; a company the linker finds is moved to "production company" by kind
# (core/responser.py), so this list only needs the generic words
_COMPANY_HINT = re.compile(
    r"\b(?:pictures|studios?|entertainment|productions?|bros\.?|brothers|company|corporation|corp\.?|inc\.?|ltd\.?"
    r"|animation|disney|pixar|dreamworks|warner|universal|paramount|miramax|lionsgate|mgm|a24|columbia"
    r"|films|cinema)\b", re.I)
_DEFAULT_REL = "director"  # wording that names no role ("X's films"); see core.filmography.role_of
# verbs that name no role ("What has X released?"): the whole filmography answers
_ROLELESS_VERB = re.compile(r"^(?:releas|put)", re.I)

# (regex, fixed relation or None to read it from group v, mention must look like a name)
_FILMS_OF = [
    (re.compile(rf"^{_PRE}{_F}\s+(?:(?:that|which)\s+)?{_AUX}?(?P<m>.+?)\s+(?P<v>{_VERB}){_TAIL}$", re.I), None, True),
    (re.compile(rf"^{_PRE}{_F}\s+(?:is|are|was|were|has|have|had)\s+(?P<m>.+?)\s+(?:been\s+)?(?:in|on)"
                r"(?:\s+(?:them|it))?$", re.I), "cast member", False),
    (re.compile(rf"^what\s+(?:{_F}\s+)?{_AUX}?(?P<m>.+?)\s+(?P<v>{_VERB}){_TAIL}$", re.I), None, True),
    (re.compile(r"^what\s+(?:has|have|had)\s+(?P<m>.+?)\s+been\s+in$", re.I), "cast member", False),
    (re.compile(rf"^{_PRE}{_F}\s+(?:(?:is|are|was|were|has\s+been|have\s+been)\s+)?"
                rf"(?P<v>directed|written|composed|scored|produced|shot|filmed|distributed|made|helmed)\s+by\s+(?P<m>.+)$",
                re.I), None, False),
    (re.compile(rf"^{_PRE}{_F}\s+with\s+(?:(?:the|a|an)\s+)?(?:music|score|soundtrack)\s+(?:by|from)\s+(?P<m>.+)$", re.I),
     "composer", False),
    (re.compile(rf"^{_PRE}{_F}\s+by\s+(?P<m>.+)$", re.I), _DEFAULT_REL, False),
    (re.compile(rf"^{_PRE}{_F}\s+(?:with|starring|featuring)\s+(?P<m>.+)$", re.I), "cast member", False),
    (re.compile(rf"^(?:which|what)\s+(?:(?P<g>[\w\-]+)\s+)?{_F}\s+(?:star|stars|feature|features)\s+(?P<m>.+)$", re.I),
     "cast member", False),
    (re.compile(rf"^{_PRE}{_FS}\s+of\s+(?P<m>.+)$", re.I), _DEFAULT_REL, True),
    # verb before the film noun: "Alfred Hitchcock directed which films?"
    (re.compile(rf"^(?P<m>.+?)\s+(?P<v>{_VERB})(?:\s+(?:in|on|for))?\s+(?:which|what)\s+(?:(?P<g>[\w\-]+)\s+)?{_F}$",
                re.I), None, True),
    (re.compile(r"^(?P<m>.+?)(?:['’]s?)?\s+(?P<v>acting|directing|writing|producing|composing|scoring)\s+"
                r"(?:credits|work|career|filmography|roles)$", re.I), None, True),
    (re.compile(r"^(?P<m>.+?)['’]s?\s+(?:acting\s+)?roles$", re.I), "cast member", True),
    (re.compile(rf"^(?P<m>.+?)['’]s?\s+(?:(?P<g>[\w\-]+)\s+)?(?:{_F}|filmography)$", re.I), _DEFAULT_REL, False),
    (re.compile(r"^(?:the\s+)?filmography\s+of\s+(?P<m>.+)$", re.I), _DEFAULT_REL, False),
    (re.compile(r"^(?P<m>.+?)\s+filmography$", re.I), _DEFAULT_REL, False),
    # no verb, no possessive: "Spielberg-produced movies", "Hans Zimmer soundtracks", "Hitchcock mystery films"
    (re.compile(rf"^(?P<m>.+?)[\s\-](?P<v>directed|written|scored|produced|composed|shot|distributed|made)\s+{_GEN}{_FS}$",
                re.I), None, True),
    (re.compile(r"^(?P<m>.+?)(?:['’]s?)?\s+(?:film\s+|movie\s+)?(?:soundtracks|scores)$", re.I), "composer", True),
    (re.compile(r"^(?P<m>.+?)(?:['’]s?)?\s+(?:screenplays|scripts)$", re.I), "screenwriter", True),
    (re.compile(rf"^(?:all\s+(?:of\s+)?)?(?:the\s+)?(?P<m>.+?)\s+{_GEN}{_FS}$", re.I), _DEFAULT_REL, True),
]

# a films_of mention that cannot be a name
_NOT_NAME_LEAD = re.compile(
    r"^(?:who|whom|whose|what|which|when|where|how|why|is|are|was|were|did|does|do|has|have|had|can|could|would"
    r"|will|should|tell|show|give|list|name|find|any|some|best|good|great|top|new|newer|newest|recent|latest|old|older"
    r"|classic|popular|famous|other|more|most|these|those|my|his|her|their|your|our|few|many|funny|scary|sad|cool"
    r"|similar|different|watch|i|you|we|a|an|and|or|of)\b", re.I)


_CLAUSE_WORD = re.compile(r"\b(?:is|was|were|are|been|being)\b", re.I)
# a modal that is also a first name, capitalized before a capitalized word: "Will Smith", "May Robson"
_MODAL_NAME = re.compile(r"^(?:Will|May)\s+[A-Z]")


def _name_like(m: str) -> bool:
    m = _tidy(m)
    if not m or (_NOT_NAME_LEAD.match(m) and not _MODAL_NAME.match(m)) or m.lower() in _GENRE_MAP \
            or _CLAUSE_WORD.search(m):
        return False
    # a company word inside the name is part of it ("studio ghibli films")
    return not any(strong for rel, (_hit, strong) in _cue_hits(m).items() if rel != "production company")


def _relation_of_verb(verb: str) -> Optional[str]:
    v = verb.lower()
    for stem, rel in _VERB_REL:
        if v.startswith(stem):
            return rel
    return None


def _parse_films_of(seg: str):
    for rx, fixed, guard in _FILMS_OF:
        m = rx.match(seg)
        if not m:
            continue
        gd = m.groupdict()
        rel = fixed or _relation_of_verb(gd["v"])
        if rel is None:
            continue
        mention = gd["m"]
        if guard and not _name_like(mention):
            continue
        # a company "makes" or "has films": production company, not director/producer
        promote = rel == "producer" or (rel == _DEFAULT_REL and (
            fixed == _DEFAULT_REL or gd["v"].lower()[:3] in ("mak", "mad") or _ROLELESS_VERB.match(gd["v"])))
        if promote and _COMPANY_HINT.search(mention):
            rel = "production company"
        return rel, mention, _genre_of(gd.get("g")), False
    return None


# --- fact forms ------------------------------------------------------------------------

# a company noun written as part of a name ("Studio Ghibli", "Walt Disney Animation Studios") is no cue
_NAME_CUE = re.compile(r"^(?:studios?|compan(?:y|ies))$", re.I)
_NAME_NEIGHBOUR_STOP = {
    "who", "whom", "what", "which", "when", "where", "how", "the", "a", "an", "is", "was", "are", "were", "did",
    "does", "do", "made", "make", "produced", "produce", "backed", "financed", "distributed", "released",
    "behind", "of", "for", "that", "in", "on", "by", "and", "tell", "me", "film", "movie",
}


def _in_name(seg: str, m) -> bool:
    word = m.group(0)
    if not _NAME_CUE.match(word) or not word[0].isupper():
        return False
    before = seg[:m.start()].split()
    after = seg[m.end():].split()

    def titled(tok):
        tok = tok.strip("?!.,;:'’\"")
        return bool(tok) and tok[0].isupper() and tok.lower() not in _NAME_NEIGHBOUR_STOP
    return (bool(after) and titled(after[0])) or (bool(before) and titled(before[-1]))


def _cue_hits(seg: str):
    """relation -> (first cue match, any strong cue) over the relation lexicon."""
    cands = {}
    for rel, frags in _COMPILED.items():
        best = None
        strong = False
        for rx, weak in frags:
            for m in rx.finditer(seg):
                if _in_name(seg, m):
                    continue
                if not weak:
                    strong = True
                if best is None or (m.start(), -m.end()) < (best.start(), -best.end()):
                    best = m
                break
        if best is not None:
            cands[rel] = (best, strong)
    return cands


def _parse_fact(seg: str):
    cands = _cue_hits(seg)
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
    if rel in _VERB_LEAD:
        post = _VERB_LEAD[rel].sub("", post.lstrip(), count=1)
    mention = _tidy(post)
    if not mention or _EMPTY_OBJECT.match(mention):
        mention = _clean_pre(pre)
    elif _PRONOUN.match(_tidy(_TRAIL[rel].sub("", mention)) if rel in _TRAIL else mention):
        # "pulp fiction who wrote it": the title stands before the question
        title = _clean_pre(_WH_TAIL.sub("", pre))
        if title and not _PRONOUN.match(title):
            mention = title
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
    count: bool = False
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    others: List[tuple] = field(default_factory=list)  # shared: (relation, mention, quoted) of the other names


# --- counts, roles, shared films -------------------------------------------------------

_COUNT = re.compile(r"^(?:how\s+many|(?:the\s+)?(?:total\s+)?number\s+of|(?:the\s+)?count\s+of)\s+", re.I)
_COUNT_TAIL = re.compile(
    r"\s+(?:(?:are|were|is)\s+there|exist|in\s+total|altogether|overall|so\s+far|in\s+the\s+(?:graph|database))$", re.I)
_THERE_MID = re.compile(
    r"^(?P<f>(?:[\w\-]+\s+)?(?:movies|films))\s+(?:are|were|is)\s+there\s+"
    r"(?=(?:with|by|starring|featuring|directed|written|produced|scored|composed|from|of)\b)", re.I)
_ROLE_WORDS = [
    (r"directors?", "director"), (r"actors?|actress(?:es)?|stars?|cast(?:\s+members?)?|performers?", "cast member"),
    (r"(?:screen)?writers?", "screenwriter"), (r"composers?", "composer"), (r"producers?", "producer"),
    (r"cinematographers?", "cinematographer"),
]
_AS_ROLE = re.compile(
    r"\s+as\s+(?:an?\s+|the\s+)?(?P<r>" + "|".join(w for w, _ in _ROLE_WORDS) + r")$", re.I)
_TOGETHER_TAIL = re.compile(r"\s+(?:together|in\s+common|with\s+each\s+other|both)$", re.I)
_BOTH_LEAD = re.compile(r"^both\s+|\s+both$", re.I)
_NAME_SPLIT = re.compile(r"\s*,\s*(?:and\s+)?|\s+(?:and|&)\s+", re.I)
_SECOND_ROLE = re.compile(
    r"\s+(?:with|and)\s+(?:(?:the|a|an)\s+)?(?P<r>music|score|soundtrack|screenplay|script|cinematography|photography)"
    r"\s+(?:by|from)\s+(?P<b>.+)$"
    r"|\s+(?:and\s+)?(?P<s>starring|featuring)\s+(?P<b2>.+)$", re.I)
_SECOND_REL = {"music": "composer", "score": "composer", "soundtrack": "composer", "screenplay": "screenwriter",
               "script": "screenwriter", "cinematography": "cinematographer", "photography": "cinematographer"}
# a second person after the verb: "movies X made with Y" (Y acted), "films X scored for Y" (Y directed)
_WITH_PERSON = re.compile(r"^(?P<head>.+?\S)\s+(?P<p>with|for|alongside)\s+(?P<b>.+)$", re.I)
_CREW = {"director", "screenwriter", "composer", "producer", "cinematographer"}

# "the director and composer of Dunkirk": one fact per noun
_NOUN = (r"(?:directors?|(?:screen)?writers?|composers?|producers?|cinematographers?|cast|actors|stars|studios?"
         r"|production\s+compan(?:y|ies)|distributors?|genres?|release\s+(?:date|year)|(?:year|date)\s+of\s+release"
         r"|countr(?:y|ies)(?:\s+of\s+origin)?|(?:original\s+)?languages?|awards?|nominations?|music|score|soundtrack"
         r"|screenplay|script)")
_NOUN_SEP = r"(?:\s*,\s*(?:and\s+)?|\s+and\s+|\s*&\s*)"
_NOUN_LIST = re.compile(
    rf"(?:^|\s)(?P<list>(?:(?:the|its)\s+)?{_NOUN}(?:{_NOUN_SEP}(?:(?:the|its)\s+)?{_NOUN})+)"
    r"\s+(?:of|for|in|on|from|behind)\s+(?P<m>.+)$", re.I)
# title first: "jaws - director and release year", "Alien: composer and cinematographer"
_NOUN_LIST_AFTER = re.compile(
    rf"^(?P<m>.+?)(?:\s*[\-–:,]\s*|\s+)(?:(?:its|the)\s+)?(?P<list>{_NOUN}(?:{_NOUN_SEP}(?:(?:the|its)\s+)?{_NOUN})+)$",
    re.I)


def _role_word(word: str) -> Optional[str]:
    for rx, rel in _ROLE_WORDS:
        if re.fullmatch(rx, word, re.I):
            return rel
    return None


def _expand_nouns(piece: str) -> List[str]:
    m = _NOUN_LIST.search(piece)
    if not m:
        m = _NOUN_LIST_AFTER.match(_trim(piece))
        if not m or _WH_LEAD.match(m.group("m")) or _ARTICLE_ONLY.match(m.group("m")) or _PRONOUN.match(m.group("m")):
            return [piece]
    nouns = [n for n in re.split(_NOUN_SEP, m.group("list"), flags=re.I) if n.strip()]
    return [f"{n.strip()} of {m.group('m')}" for n in nouns]


_VERB_END = re.compile(rf"\s(?:{_VERB})(?:\s+(?:in|on))?$", re.I)
_NOT_PERSON_LEAD = re.compile(r"^(?:the|a|an|my|his|her|their|our|your|kids?|children|family|fun|friends?)\b", re.I)


def _person_like(s: str) -> bool:
    """A second name after with/for: two words or a capital, and no 'the kids' / 'my family'."""
    s = _tidy(s)
    if not _name_like(s) or _NOT_PERSON_LEAD.match(s):
        return False
    return len(s.split()) >= 2 or s[:1].isupper()


def _films_of_with_others(seg: str):
    """films_of parse plus the other names of a shared question. Returns (hit, others) or (None, [])."""
    seg = _trim(_TOGETHER_TAIL.sub("", seg))
    m = _SECOND_ROLE.search(seg)
    if m:
        hit = _parse_films_of(seg[:m.start()])
        if hit is not None:
            rel2 = _SECOND_REL[m.group("r").lower()] if m.group("r") else "cast member"
            return hit, [(rel2, m.group("b") or m.group("b2"))]
    m = _WITH_PERSON.match(seg)
    if m and _person_like(m.group("b")):
        hit = _parse_films_of(m.group("head"))
        # only after a role verb ("made", "scored", "starred in"): "films with X" is a plain cast list
        if hit is not None and _VERB_END.search(m.group("head")):
            rel = hit[0]
            if m.group("p").lower() == "for":
                rel2 = "director" if rel != "director" else "producer"
            else:
                rel2 = "cast member" if rel in _CREW or rel == "cast member" else None
            if rel2:
                return hit, [(rel2, m.group("b"))]
    hit = _parse_films_of(seg)
    if hit is None:
        return None, []
    rel, mention, genre, weak = hit
    mention = _BOTH_LEAD.sub("", mention)
    names = [n for n in _NAME_SPLIT.split(mention) if n.strip()]
    # "X and Y movies", "films with X and Y": films of every name (a person's name holds no "and")
    if len(names) >= 2:
        return (rel, names[0], genre, weak), [(rel, n) for n in names[1:]]
    return (rel, mention, genre, weak), []


def _parse_segment(seg: str, quotes: List[str]) -> Optional[_Seg]:
    seg = _lead_strip(_trim(seg))
    while True:
        t = _trim(_CHAT_TRAIL.sub("", seg))
        if t == seg:
            break
        seg = t
    count = False
    m = _COUNT.match(seg)
    if m:
        count, seg = True, seg[m.end():]
        seg = _THERE_MID.sub(lambda x: x.group("f") + " ", seg)
        seg = _trim(_COUNT_TAIL.sub("", seg))
    seg, year_from, year_to = _take_range(seg)
    seg = _genre_nouns(seg)
    role = None
    m = _AS_ROLE.search(seg)
    if m:
        role, seg = _role_word(m.group("r")), _trim(seg[:m.start()])
    seg, year = _take_year(seg)
    hit, others = _films_of_with_others(seg)
    if hit is None and role is not None and _name_like(seg):
        hit = (role, seg, None, False)  # "Greta Gerwig as director"
    if hit is not None:
        rel, mention, genre, weak = hit
        if role is not None:
            rel = role
        kind, trail = ("shared" if others else "count" if count else "films_of"), None
        if year is not None and year_from is None and year_to is None:
            year_from = year_to = year  # "Tom Hanks films from 1994": a range, not a title year
            year = None
    else:
        fact = _parse_fact(seg)
        if fact is None:
            return None
        rel, mention, genre, weak, trail = fact
        kind = "fact"
    mention = _finish_mention(mention, rel, trail, fact=(kind == "fact"))
    if year is None and kind == "fact" and not _PLACEHOLDER.search(mention):
        m = _YEAR_BARE.match(mention)
        if m and _valid_year(m.group("y")) and not _ARTICLE_ONLY.match(m.group("t")):
            year = _valid_year(m.group("y"))
            mention = m.group("t")
    text, quoted, pron = _resolve(mention, quotes)
    rest = []
    for r2, m2 in others:
        t2, q2, _p = _resolve(_finish_mention(m2, r2, None, fact=False), quotes)
        if t2:
            rest.append((r2, t2, q2))
    return _Seg(kind, rel, text, quoted, year, genre, weak, inherits=pron, count=count,
                year_from=year_from, year_to=year_to, others=rest)


def _unknown() -> Intent:
    return Intent(kind="unknown", relation=None, mention=None, confidence=CONF_NONE)


def parse_intent(question: str) -> Intent:
    text, quotes = _protect_quotes(question or "")
    text = _denoise(re.sub(r"\s+", " ", text).strip())
    if not text or _NOT_FACTUAL.search(text):
        return _unknown()
    segs = []
    for piece in _SPLIT.split(text):
        if not piece or not piece.strip():
            continue
        for sub in _expand_nouns(piece):
            s = _parse_segment(sub, quotes)
            if s is not None:
                segs.append(s)
    if not segs:
        return _unknown()
    top = segs[0]
    if top.kind == "fact" and top.mention is None and top.inherits:
        # "Who wrote and directed Jaws?": the first part takes the subject of the next one
        nxt = next((s for s in segs[1:] if s.kind == "fact" and s.mention), None)
        if nxt is not None:
            top.mention, top.quoted, top.inherits = nxt.mention, nxt.quoted, False
            top.year = top.year if top.year is not None else nxt.year
    intents = []
    for i, s in enumerate(segs):
        mention, quoted, year = s.mention, s.quoted, s.year
        if i > 0 and mention and not quoted and _THE_PART.match(mention):
            mention, s.inherits = None, True   # "... and who composed the music?": the first part's film
        if i > 0 and mention is None and s.inherits:
            mention, quoted = top.mention, top.quoted
            year = year if year is not None else top.year
        it = Intent(
            kind=s.kind, relation=s.relation, mention=mention, quoted=quoted, year=year, genre=s.genre,
            confidence=_confidence(s.relation, mention, s.weak), count=s.count,
            year_from=s.year_from, year_to=s.year_to)
        # shared: the other names are films_of parts with the same filters
        it.parts = [Intent(kind="films_of", relation=r2, mention=m2, quoted=q2, genre=s.genre,
                           confidence=_confidence(r2, m2, False), year_from=s.year_from, year_to=s.year_to)
                    for r2, m2, q2 in s.others]
        intents.append(it)
    result = intents[0]
    for extra in intents[1:]:
        result.parts.append(extra)
    return result
