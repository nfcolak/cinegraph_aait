# relation.py
# Relation (property) parsing and local resolution (ENGLISH ONLY).
# - Detect a canonical relation label from the user's question via regex.
# - Resolve the property URI from the local graph using English rdfs:label,
#   with hard-coded WDT URI fallbacks if labels are missing in the graph.

import re
from rdflib import URIRef

# Minimal, extensible patterns mapping to canonical property labels.
# Make sure these labels exist in your graph or are covered by FALLBACK_PRED_URIS.
_PATTERNS = [
    # Cast member (e.g., wdt:P161) - both inverse and forward queries
    (r"\b(?:star|act|appear)\s+in\b", "cast member"),
    (r"\bwhich\s+(?:movies?|films?)\s+(?:did|does)\s+\w+.*(?:star|act|appear)\b", "cast member"),
    (r"\b(?:what|which)\s+(?:movies?|films?)\s+star\s+.+", "cast member"),
    (r"\b(?:what|which)\s+(?:movies?|films?)\s+(?:feature|featuring)\s+.+", "cast member"),
    (r"\b(?:movies?|films?)\s+(?:with|starring|featuring)\s+.+", "cast member"),
    (r"\bhas\s+.+\s+as\s+cast\s+member\b", "cast member"),
    (r"\b(?:have|has)\s+.+\s+(?:as|in)\s+(?:the\s+)?cast\b", "cast member"),
    (r"\bcast\s+(?:of|in|for)\b", "cast member"),
    (r"\bwho\s+(?:is|are|were|was)\s+(?:in\s+)?(?:the\s+)?cast\b", "cast member"),
    (r"\bcast\s+members?\b", "cast member"),
    (r"\bwho\s+(?:starred|stars|acts|acted)\s+in\b", "cast member"),

    # Director (e.g., wdt:P57)
    (r"\bwho\s+directed\b", "director"),
    (r"\bdirected\s+by\b", "director"),
    (r"\bthe\s*director\b", "director"),
    (r"\b(who|director)\s+(?:made|makes|directed)\b", "director"),
    # Inverse patterns with optional genre - "which [genre] movies did X direct"
    (r"\bwhich\s+(?:[\w\-]+\s+)?(?:movies?|films?)\s+(?:did|does)\s+.+\s+direct\b", "director"),
    (r"\b(?:which|what)\s+(?:[\w\-]+\s+)?(?:movies?|films?)\s+(?:were|was)\s+directed\s+by\b", "director"),

    # Screenwriter (e.g., wdt:P58)
    (r"\b(?:what|which)\s+(?:[\w\-]+\s+)?(?:movies?|films?)\s+(?:did|does|has|have)\s+.+\s+(?:write|wrote)\b", "screenwriter"),
    (r"\b(screenwriter|who\s+wrote|written\s+by|scenarist)\b", "screenwriter"),
    (r"\bwriter\s+(?:is|of|for)\b", "screenwriter"),

    # Composer (e.g., wdt:P86)
    (r"\bwho\s+(is|was)\s+the\s+composer\b", "composer"),
    (r"\bcomposer\s+of\b", "composer"),
    (r"\bwho\s+composed\b", "composer"),
    (r"\bcomposed\s+by\b", "composer"),
    (r"\bthe\s+composer\b", "composer"),
    (r"\bwhich\s+(?:[\w\-]+\s+)?(?:movies?|films?)\s+(?:did|does)\s+.+\s+compose\b", "composer"),
    (r"\b(?:which|what)\s+(?:[\w\-]+\s+)?(?:movies?|films?)\s+(?:were|was)\s+composed\s+by\b", "composer"),

    # Production Company (e.g., wdt:P272) — checked before Producer to avoid conflicts
    (r"\bproduction\s+compan(?:y|ies)\b", "production company"),
    (r"\bstudio\b", "production company"),
    (r"\bmade\s+by\s+(?:which|what)\s+(?:company|studio)\b", "production company"),
    (r"\bwhich\s+(?:company|studio)\s+(?:produced|made)\b", "production company"),
    (r"\bwho\s+produced\s+(?:the\s+)?(?:film|movie)\b", "production company"),
    (r"\b(?:movies?|films?)\s+(?:were|was)\s+produced\s+by\b", "production company"),
    (r"\bproduced\s+by\s+[A-Z]", "production company"),  # "produced by Warner"

    # Producer (e.g., wdt:P162) - person, not company
    (r"\b(who|what\s+person)\s+(?:is|was)\s+(?:the\s+)?producer\b", "producer"),

    # Distributor (e.g., wdt:P750)
    (r"\bdistributed\s+by\b", "distributed by"),
    (r"\bdistributor\b", "distributed by"),
    (r"\bwhich\s+(?:company|studio)\s+distributed\b", "distributed by"),

    # Cinematographer (e.g., wdt:P344)
    (r"\bcinematographer\b", "cinematographer"),

    # Awards/Nominations (e.g., wdt:P1411, wdt:P166)
    (r"\bnominated\s+for\b", "nominated for"),
    (r"\bwhat\s+awards.*nominated\b", "nominated for"),
    (r"\bwhich\s+awards.*nominated\b", "nominated for"),
    (r"\bawards.*nominated\b", "nominated for"),
    (r"\breceived.*award\b", "award received"),
    (r"\bwhat\s+awards.*received\b", "award received"),
    (r"\b(?:which|what)\s+(?:movies?|films?)\s+(?:won|have\s+won)\s+awards?\b", "award received"),

    # Genre (e.g., wdt:P136)
    (r"\bwhat\s+genre\b", "genre"),
    (r"\bwhich\s+genre\b", "genre"),
    (r"\bgenres?\b", "genre"),

    # Country of origin (e.g., wdt:P495)
    (r"\bfrom\s+(what|which)\s+country\b", "country of origin"),
    (r"\bcountry\s+of\s+origin\b", "country of origin"),
    (r"\bcountry\s+(?:is|was)\b", "country of origin"),

    # Original Language (e.g., wdt:P364)
    (r"\bhave\s+original\s+language\b", "original language"),
    (r"\b(original\s+)?language\b", "original language"),

    # Publication/Release date (e.g., wdt:P577)
    (r"\bwhen\b.*\b(released?|come\s+out|publication\s+date|premiere)\b", "publication date"),
    (r"\brelease\s+date\b", "publication date"),
    (r"\bpublication\s+date\b", "publication date"),
]

# Hard-coded fallbacks for common WDT properties.
FALLBACK_PRED_URIS = {
    "cast member": "http://www.wikidata.org/prop/direct/P161",
    "director": "http://www.wikidata.org/prop/direct/P57",
    "screenwriter": "http://www.wikidata.org/prop/direct/P58",
    "composer": "http://www.wikidata.org/prop/direct/P86",
    "producer": "http://www.wikidata.org/prop/direct/P162",
    "production company": "http://www.wikidata.org/prop/direct/P272",
    "distributed by": "http://www.wikidata.org/prop/direct/P750",
    "cinematographer": "http://www.wikidata.org/prop/direct/P344",
    "nominated for": "http://www.wikidata.org/prop/direct/P1411",
    "award received": "http://www.wikidata.org/prop/direct/P166",
    "genre": "http://www.wikidata.org/prop/direct/P136",
    "country of origin": "http://www.wikidata.org/prop/direct/P495",
    "original language": "http://www.wikidata.org/prop/direct/P364",
    "publication date": "http://www.wikidata.org/prop/direct/P577",
}


def parse_relation(question: str):
    """
    Return a canonical relation label inferred from the question text, or None.
    Matching is case-insensitive and based on simple regex patterns above.
    """
    q = question.lower()
    for pat, label in _PATTERNS:
        if re.search(pat, q):
            return label
    return None


def resolve_property_uri_from_local(pred_lbl_to_uri: dict, label: str):
    """
    Resolve a property URI from a canonical label.

    Order:
      1) Try the local map built from English rdfs:label (label -> URI).
      2) Fall back to a hard-coded WDT URI for common properties.

    Args:
        pred_lbl_to_uri: Dict[str -> rdflib.term.URIRef], keys are lowercased labels.
        label: Canonical label detected by parse_relation (e.g., "director").

    Returns:
        rdflib.term.URIRef or None if not found.
    """
    if not label:
        return None

    # 1) Local label map
    uri = pred_lbl_to_uri.get(label.lower())
    if uri:
        return uri

    # 2) WDT fallback
    fb = FALLBACK_PRED_URIS.get(label.lower())
    return URIRef(fb) if fb else None