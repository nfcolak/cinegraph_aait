# entity.py
# Entity parsing and resolution against the local RDF graph (English labels prioritized).

import re

# Normalize smart quotes to plain ASCII quotes so quoted-title extraction works reliably.
_SMART = str.maketrans({
    "“": '"', "”": '"', "„": '"',
    "‘": "'", "’": "'", "‚": "'",
})

_ARTICLE_RE = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)


def _normalize_quotes(s: str) -> str:
    """Replace smart quotes with plain quotes."""
    return s.translate(_SMART)


def _clean(segment: str) -> str:
    return segment.strip(" \t\n\r-—–,.?!\"'")


def extract_person_name(text: str):
    """
    Extract a person's name from inverse queries like "Which movies did Eva Green direct?".
    Returns the person's name or None.
    """
    t = _normalize_quotes(text)

    # Pattern: "which/what movies/films did [Name] <verb>"
    # E.g., "Which movies did Eva Green direct?"
    patterns = [
        # Handle "has/have [Name] as cast member"
        r'(?:which|what)\s+(?:[\w\-]+\s+)?(?:movies?|films?)\s+(?:has|have)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\s+as\s+(?:cast\s+member|cast)',

        # Handle genre-qualified queries like "Which biographical movies did Meryl Streep star in?"
        r'(?:which|what)\s+(?:[\w\-]+\s+)?(?:movies?|films?)\s+(?:did|does|has|have)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\s+(?:star|act|appear)\s+in',

        # Generic "Which movies did [Name] direct/star/act/...?"
        r'(?:which|what)\s+(?:movies?|films?)\s+(?:did|does|has|have)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\s+(?:direct|star|act|write|compose|produce)',

        r'(?:which|what)\s+(?:movies?|films?)\s+(?:was|were)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\s+(?:in|a\s+(?:director|actor|writer|composer|producer))',
        r'(?:which|what)\s+(?:movies?|films?)\s+(?:were|was)\s+directed\s+by\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',
        r'(?:which|what)\s+(?:movies?|films?)\s+(?:were|was)\s+written\s+by\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',
        r'(?:which|what)\s+(?:movies?|films?)\s+star\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',
        r'(?:which|what)\s+(?:movies?|films?)\s+(?:feature|featuring|with)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',
        r'(?:which|what)\s+(?:movies?|films?)\s+(?:won|have\s+won)\s+awards?\s+for\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',

        # "Movies with Tom Hanks"
        r'^(?:movies?|films?)\s+(?:with|starring|featuring)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',

        # Explicitly handle "What films star Johnny Depp"
        r'(?:what|which)\s+(?:films?|movies?)\s+star\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',
    ]

    for pattern in patterns:
        match = re.search(pattern, t, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            return name

    return None


def extract_title(text: str):
    """
    Extract a movie/work title from the question.
    Order:
      1) First quoted span (single or double quotes, including smart quotes)
      2) Natural question patterns (e.g., "What is the director of Titanic?")
      3) Fallback: pattern like 'movie <title>' or 'film <title>'
    Returns the inner string or None.
    """
    t = _normalize_quotes(text)

    # 1) Quoted title
    matches = re.findall(r"'([^']+)'|\"([^\"]+)\"", t)
    titles = [(a or b).strip() for (a, b) in matches if (a or b)]
    if titles:
        return titles[0]

    # 2) Natural question patterns
    # "What/Who is/was the <property> of <TITLE>?"
    # Examples: "What is the director of Titanic?", "Who is the composer of Inception?"
    prop_pattern = (
        r"(?:what|who|which)\s+(?:is|was|are|were)\s+(?:the\s+)?"
        r"(?:director|genre|composer|screenwriter|writer|producers?"
        r"|production\s+company|cast|cinematographer|music|soundtrack"
        r"|award(?:s)?|awards?|release\s+date|publication\s+date)"
        r"\s+(?:of|for)\s+(.+?)(?:[\?\.!,\-]|$)"
    )
    match = re.search(prop_pattern, t, flags=re.IGNORECASE)
    if match:
        title = _clean(match.group(1))
        if title:
            return title

    # 3) Verb-based pattern: "Who directed Titanic?"
    verb_pattern = (
        r"(?:who|which)\s+(?:directed|wrote|composed|produced|made|created)\s+"
        r"(?:the\s+)?(?:movie|film)?\s*(.+?)(?:[\?\.!,\-]|$)"
    )
    match = re.search(verb_pattern, t, flags=re.IGNORECASE)
    if match:
        title = _clean(match.group(1))
        if title:
            return title

    # 4) Release/date pattern: "When was Titanic released?"
    release_patterns = [
        r"(?:when|what)\s+(?:is|was|were)?\s*(?:the\s+)?"
        r"(?:release|premiere|publication)\s+(?:date\s+of\s+|for\s+)?"
        r"(.+?)(?:[\?\.!,\-]|$)",

        r"(?:when)\s+(?:was|did)\s+(?:the\s+)?(.+?)\s+"
        r"(?:get\s+released|get\s+premiered|get\s+published|release|premiere|come\s+out|debut)"
        r"(?:[\?\.!,\-]|$)",

        r"(?:when)\s+(?:was|did)\s+(?:the\s+)?(.+?)\s+"
        r"(?:released|premiered|published)(?:[\?\.!,\-]|$)",
    ]
    for pattern in release_patterns:
        match = re.search(pattern, t, flags=re.IGNORECASE)
        if match:
            title = _clean(match.group(1))
            if title:
                return title

    # 5) Fallback: "… movie <title> ?" (grab up to question mark or end)
    m2 = re.search(r"\b(movie|film)\s+(.+?)(\?|$)", t, flags=re.IGNORECASE)
    if m2:
        title = _clean(m2.group(2))
        if title:
            return title

    # 6) Last resort: grab the longest capitalized phrase (best-effort)
    capital_candidates = re.findall(r"([A-Z][\w]*(?:\s+[A-Z][\w]*)+)", text)
    if capital_candidates:
        for candidate in reversed(capital_candidates):
            cleaned = _clean(candidate)
            if cleaned:
                return cleaned

    return None


def resolve_entity(graph, lbl_to_ent: dict, text: str):
    """
    Resolve an entity mention to subjects in the graph.

    Strategy:
      1) Exact English rdfs:label via the provided lbl_to_ent map (case-sensitive).
      2) Article-stripped exact match (case-sensitive).
      3) SPARQL for exact/case-insensitive match (faster than CONTAINS).
      4) Substring match on any-language rdfs:label (SPARQL fallback - kept for robustness).

    Args:
        graph: The RDF graph
        lbl_to_ent: Dict mapping exact English labels to URIs
        text: The entity text to resolve

    Returns:
      List[rdflib.term.URIRef] (may be empty).
    """
    if not text:
        return []

    # --- 1 & 2: Exact Label Matches (Highest Priority) ---
    exact_match_uris = []

    def _try_label_map(candidates):
        hits = []
        for cand in candidates:
            if not cand:
                continue
            key = cand.strip()
            if key and key in lbl_to_ent:
                hits.append(lbl_to_ent[key])
        return hits

    # Build candidate strings: raw text, title-cased, stripped articles, and re-added articles
    candidates = {text}
    candidates.add(text.title())

    stripped = _ARTICLE_RE.sub("", text).strip()
    if stripped:
        candidates.add(stripped)
        candidates.add(stripped.title())

        # If the original input lacked an article, try adding "The ...".
        if not _ARTICLE_RE.match(text):
            candidates.add(f"The {stripped}")
            candidates.add(f"The {stripped}".title())

    exact_match_uris.extend(_try_label_map(candidates))

    if exact_match_uris:
        # If we have an exact hit, prioritize only those URIs.
        # Further prioritization by type will happen elsewhere (e.g., responser.py)
        return list(set(exact_match_uris))

    # --- 3 & 4 through the linker's label index when it is built (the SPARQL scans take seconds) ---
    from core.linker import peek_linker, normalize, STOP
    linker = peek_linker(graph)
    if linker is not None:
        key = normalize(text)
        if not key:
            return []
        if key in linker.index:
            return list(linker.index[key])[:10]
        toks = [t for t in key.split() if t not in STOP and t in linker.tok]
        if not toks or len(toks) < len([t for t in key.split() if t not in STOP]):
            return []  # a word no label has: no label contains the text
        rare = min(toks, key=lambda t: len(linker.tok[t]))
        hits = sorted((linker.keys[i] for i in linker.tok[rare] if key in linker.keys[i]), key=len)
        out = []
        for k in hits:
            out.extend(u for u in linker.index[k] if u not in out)
            if len(out) >= 10:
                break
        return out[:10]

    # --- 3: Case-Insensitive Exact Match (SPARQL) ---
    safe = text.replace("\\", r"\\").replace('"', r"\"")

    # Check for exact, case-insensitive match
    rows = list(graph.query(f"""
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?s WHERE {{
          ?s rdfs:label ?l .
          FILTER (lcase(str(?l)) = lcase("{safe}"))
        }}
        LIMIT 10
    """))
    exact_uris = [r[0] for r in rows]
    if exact_uris:
        return exact_uris

    # --- 4: Substring Fallback (Lowest Priority) ---
    # Only if we couldn't find an exact match above
    rows = list(graph.query(f"""
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?s WHERE {{
          ?s rdfs:label ?l .
          FILTER (CONTAINS(lcase(str(?l)), lcase("{safe}")))
        }}
        LIMIT 10
    """))
    return [r[0] for r in rows]
