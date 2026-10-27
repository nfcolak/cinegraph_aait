# recommender.py
# Content-based movie recommendation system using RDF graph properties

import re
from dataclasses import dataclass
from typing import Any, List, Dict, Set, Tuple, Optional
import rdflib
from rdflib.namespace import RDFS
import numpy as np


# --- Embedding configuration (set from Responser) ---
_ENTITY_EMBEDS = None
_ENT_URI_TO_ID = None
_EMBED_WEIGHT = 0.4  # Influence of embedding similarity in final score (increased for diversity)
_MIN_VECTOR_NORM = 1e-9

# Metadata gating constants
_PROPERTY_SIM_THRESHOLD = 0.18

# URIs behind the last recommend_movies / recommend_by_theme call: 'seeds' (resolved seed films)
# and 'recommendations' (label -> URI), so callers can show the exact films, not same-named ones.
LAST_RUN: Dict[str, Any] = {'seeds': [], 'seed_names': [], 'recommendations': {}}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _resolve_seeds(graph, title: str) -> Tuple[List[rdflib.URIRef], Optional[str]]:
    """
    Seed title -> (film URIs, display name). A series or character named exactly
    ("movies like Star Wars", "like Harry Potter") stands for its films. Uses the entity
    linker when one is built for this graph (typo-tolerant), else the label scan.
    """
    from core.linker import peek_linker

    linker = peek_linker(graph)
    if linker is None:
        uri = resolve_movie_uri(graph, title)
        return ([uri], None) if uri else ([], None)

    # the linked label must cover most of what was typed ("recommend something" is not "Rec")
    def covers(c) -> bool:
        return c.match == "exact" or len(_norm(c.label)) >= 0.6 * len(_norm(title))

    films = [c for c in linker.link(title, want={'film'}, limit=3) if c.kind == 'film' and covers(c)]
    if films and films[0].match == "exact":
        return [rdflib.URIRef(films[0].uri)], films[0].label
    # no film with this exact title: a series or character stands for its films
    groups = []
    for c in linker.link(title, want={'series', 'character'}, limit=6):
        if c.kind in ("series", "character") and covers(c):
            linked = linker.films_of_entity(c.uri)
            if linked:
                groups.append((c.match == "exact", len(linked), c, linked))
    if groups:
        _exact, _n, c, linked = max(groups, key=lambda g: (g[0], g[1]))
        return [rdflib.URIRef(f) for f in linked[:15]], c.label
    if films:
        return [rdflib.URIRef(films[0].uri)], films[0].label
    return [], None


@dataclass
class MovieProfile:
    """Locally cached view of a movie's metadata."""
    uri: rdflib.URIRef
    label: Optional[str]
    properties: Dict[str, Set[str]]
    rating: Optional[float]
    embedding_id: Optional[int]


# Cache movie profiles so we do not keep re-reading heavy property lists
_MOVIE_PROFILE_CACHE: Dict[str, MovieProfile] = {}


def configure_embedding_similarity(entity_embeds=None, ent_uri_to_id=None, weight: float = 0.35):
    """
    Provide optional embedding resources so the recommender can blend
    metadata-based and embedding-based similarity scores.
    """
    global _ENTITY_EMBEDS, _ENT_URI_TO_ID, _EMBED_WEIGHT
    _ENTITY_EMBEDS = entity_embeds
    _ENT_URI_TO_ID = ent_uri_to_id

    if weight is not None:
        # Clamp weight to [0, 1]
        _EMBED_WEIGHT = max(0.0, min(1.0, float(weight)))


def _has_embedding_data() -> bool:
    return _ENTITY_EMBEDS is not None and _ENT_URI_TO_ID is not None


def _resolve_embedding_id(uri) -> Optional[int]:
    if not _has_embedding_data():
        return None
    return _ENT_URI_TO_ID.get(str(uri))


def _get_movie_label(graph, movie_uri: rdflib.URIRef) -> Optional[str]:
    for obj in graph.objects(movie_uri, RDFS.label):
        label = str(obj).strip()
        if label:
            return label
    return None


def _build_movie_profile(graph, movie_uri: rdflib.URIRef) -> MovieProfile:
    props = get_movie_properties(graph, movie_uri)
    label = _get_movie_label(graph, movie_uri)
    rating = get_movie_rating(graph, movie_uri)
    embedding_id = _resolve_embedding_id(movie_uri)
    return MovieProfile(uri=movie_uri, label=label, properties=props, rating=rating, embedding_id=embedding_id)


def _get_movie_profile(graph, movie_uri: rdflib.URIRef) -> MovieProfile:
    key = str(movie_uri)
    profile = _MOVIE_PROFILE_CACHE.get(key)
    if profile is not None:
        return profile
    profile = _build_movie_profile(graph, movie_uri)
    _MOVIE_PROFILE_CACHE[key] = profile
    return profile


def _embedding_similarity(seed_ids: List[int], candidate_id: Optional[int]) -> float:
    """
    Average cosine similarity between the candidate movie and each seed movie.
    Returns value in [0, 1], or 0 if vectors are unavailable.
    """
    if not seed_ids or candidate_id is None or not _has_embedding_data():
        return 0.0

    cand_vec = _ENTITY_EMBEDS[candidate_id]
    cand_norm = np.linalg.norm(cand_vec)
    if cand_norm < _MIN_VECTOR_NORM:
        return 0.0

    sims = []
    for sid in seed_ids:
        seed_vec = _ENTITY_EMBEDS[sid]
        seed_norm = np.linalg.norm(seed_vec)
        denom = seed_norm * cand_norm
        if denom < _MIN_VECTOR_NORM:
            continue
        cos_sim = float(np.dot(seed_vec, cand_vec) / denom)
        cos_sim = max(-1.0, min(1.0, cos_sim))
        sims.append((cos_sim + 1.0) / 2.0)  # map [-1,1] -> [0,1]

    if not sims:
        return 0.0
    return float(sum(sims) / len(sims))


def extract_movie_titles(text: str) -> List[str]:
    """
    Extract movie titles from text using a general approach.
    Looks for quoted strings or titles after common trigger phrases.
    """
    titles = []

    # Pattern 1: Quoted titles (always check first)
    # Match both single and double quotes, but separately to avoid mixing
    # Double quotes first (higher priority)
    double_quoted = re.findall(r'"([^"]+)"', text)
    titles.extend(double_quoted)

    # Single quotes (only if not already found in double quotes)
    single_quoted = re.findall(r"'([^']+)'", text)
    for sq in single_quoted:
        # Avoid duplicates and filter out very short strings (likely apostrophes)
        if sq not in titles and len(sq) > 2:
            titles.append(sq)

    # Pattern 2: General trigger phrases followed by movie titles
    # This captures: "similar to X", "like X", "enjoyed X", "loved X", "vibe as X", etc.
    # Stop capturing at constraint phrases (that/with/where/having)
    trigger_patterns = [
        # Most specific patterns first (with clear ending markers)
        r"I\s+(?:really\s+)?(?:love|loved|enjoy|enjoyed|like|liked)\s+(.+?)\s*[—\-–]\s*(?:what|can\s+you)",
        r"(?:I(?:'m|\s+am)\s+)?(?:a\s+fan\s+of)\s+(.+?)\s*[—\-–]\s*(?:what|can\s+you)",
        # Simple "I [verb] X" patterns - allow appearing mid-sentence too
        r"^I\s+(?:really\s+)?(?:love|loved|enjoy|enjoyed|like|liked|watched)\s+(.+?)(?:\s+(?:so|but|because|since)\s+|\s*$)",
        r"I\s+(?:really\s+)?(?:love|loved|enjoy|enjoyed|like|liked|watched)\s+(.+?)(?:\s+(?:so|but|because|since)\s+|[\.!?]|$)",
        r"(?:since|given\s+that|if|after)\s+(?:I(?:'m|\s+am)?\s+)?(?:into|watching|love|loved|enjoy|enjoyed|like|liked)\s+(.+?)(?:\s+(?:that|with|where|having)|,\s*(?:what|which|can)|[\?]|$)",
        r"(?:I(?:'m|\s+am)\s+)?(?:a\s+fan\s+of|into|big\s+on)\s+(.+?)(?:\s+(?:that|with|where|having)|,\s*(?:what|which|can)|[\?]|$)",
        # "movies with X like Y" pattern - captures Y (the examples)
        r"(?:films?|movies?)\s+with\s+.+?\s+like\s+(.+?)(?:\s+(?:that|with|where|having)|[\?]|$)",
        # Less specific patterns (broader matches) - stop at constraint words or "and"
        r"similar\s+(?:movies?|films?|ones?|titles?|stuff)\s+(?:to|as)\s+(.+?)(?:\s+(?:that|with|where|having)|[\.?!]|$)",
        r"(?:something|anything|more|others?|ones?|stuff)\s+(?:like|similar\s+to)\s+(.+?)(?:\s+(?:that|with|where|having)|[\.?!,]|$)",
        r"similar\s+to\s+(.+?)(?:\s+(?:that|with|where|having)|[\.?]|$)",
        r"(?:same|similar)\s+(?:vibe|feel|style|tone|atmosphere)\s+as\s+(.+?)(?:\s+(?:that|with|where|having)|[\?]|$)",
        r"(?:films?|movies?)\s+(?:like|similar\s+to|in\s+that\s+style)\s+(.+?)(?:\s+(?:that|with|where|having)|[\?]|$)",
        r"in\s+(?:that|the\s+same)\s+(?:style|vein)\s+as\s+(.+?)(?:\s+(?:that|with|where|having)|[\?]|$)",
        r"that\s+(?:feel|are)\s+like\s+(.+?)(?:\s+(?:that|with|where|having)|[\.\?]|$)",
        # Pattern for "fans of X would enjoy" or "that fans of X would like"
        r"(?:that\s+)?fans\s+of\s+(.+?)(?:\s+(?:would|might|will|should)|\s*$)",
        # Title first: "Chicken Little similar", "Shrek-like movies", "movies Toy Story fans like"
        r"^(?:(?:movies?|films?)\s+)?(.+?)\s+(?:similar|alike|lookalikes?|recommendations?)(?:\s+(?:movies?|films?))?\s*[\.?!]*$",
        r"^(.+?)[\s\-]like\s+(?:movies?|films?)\s*[\.?!]*$",
        # "what to watch after Frozen", "after watching Up, what next?"
        r"(?:watch|see)\s+(?:next\s+)?(?:after|following)\s+(.+?)(?:\s+(?:that|with|where|having)|[\.?!,]|$)",
        r"after\s+(?:watching|seeing)\s+(.+?)(?:\s+(?:that|with|where|having)|[\.?!,]|$)",
    ]

    # Try each trigger pattern
    for pattern in trigger_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            items = match.group(1).strip()
            # Skip if it's just a reference word
            if items.lower() in ['it', 'that', 'this', 'them']:
                continue

            # Split by commas, "and", and "or"
            # First, split by comma (highest priority separator)
            parts = re.split(r',\s*', items)

            # For each part, check if it contains " and " or " or " that separates titles
            # Strategy: Split on "and"/"or", then recombine if the next word is an article
            # Example: "Beauty and the Beast and Pocahontas" ->
            #   ["Beauty", "the Beast", "Pocahontas"] -> ["Beauty and the Beast", "Pocahontas"]
            # Special case: If there's only ONE "and"/"or" and no commas, assume it's a single title
            expanded_parts = []
            for part in parts:
                # Split on "and" and "or", capturing the separator
                tokens = re.split(r'\s+(and|or)\s+', part, flags=re.IGNORECASE)
                if len(tokens) == 1:
                    # No "and"/"or" found
                    expanded_parts.append(part)
                elif len(tokens) == 3 and len(parts) == 1:
                    # Special case: exactly one "and"/"or" and no commas in original input
                    # NEW HEURISTIC: Check word counts on BOTH sides
                    # - "Beauty and the Beast" → ONE title (left=1, right=2-3 with article)
                    # - "Forrest Gump and The Lord of the Rings" → TWO titles (left=2, right=5+ even with article)
                    left_part = tokens[0].strip()
                    right_part = tokens[2].strip()
                    left_word_count = len(left_part.split())
                    right_word_count = len(right_part.split())
                    right_first_word = right_part.split()[0] if right_part else ''

                    # Check if it's "X and the Y" pattern (single title)
                    if right_first_word.lower() in ['the', 'a', 'an']:
                        # Article after "and" - check both left and right lengths
                        if left_word_count == 1 and right_word_count <= 3:
                            # "Beauty and the Beast" → ONE title
                            expanded_parts.append(part)
                        else:
                            # "Forrest Gump and The Lord of the Rings" → TWO titles
                            # (left=2 words, or right>3 words)
                            expanded_parts.append(tokens[0])
                            expanded_parts.append(tokens[2])
                    else:
                        # No article - always split
                        # "Moana and Frozen", "Cars and Ratatouille"
                        expanded_parts.append(tokens[0])
                        expanded_parts.append(tokens[2])
                else:
                    # Reconstruct intelligently:
                    # - "X and the Y" -> keep together (article after "and")
                    # - "X and Y" where Y is capitalized non-article -> likely separate title
                    # - Pattern like "Pride and Prejudice and Sense and Sensibility":
                    #   After building "Pride and Prejudice", next "and" + capitalized word starts new title

                    # NEW HEURISTIC: If there are many "and"s (len(tokens) >= 5), assume each capitalized
                    # non-article word after "and" is a new title
                    aggressive_split = len(tokens) >= 5

                    current_title = tokens[0]
                    i = 1
                    while i < len(tokens):
                        if i + 1 < len(tokens):
                            separator = tokens[i]  # "and" or "or"
                            next_part = tokens[i + 1]
                            next_word = next_part.split()[0] if next_part.strip() else ''

                            # If next word starts with article, check if we should still split
                            if next_word.lower() in ['the', 'a', 'an']:
                                # SPECIAL CASE: In aggressive mode, "and the X" likely starts new title
                                # UNLESS current_title is very short (1-2 words) suggesting it's part of same title
                                if aggressive_split and len(current_title.split()) >= 1:
                                    # "and the Lion King" after "Pocahontas" → new title
                                    if current_title.strip():
                                        expanded_parts.append(current_title)
                                    current_title = next_part
                                    i += 2
                                else:
                                    # "Pride and the..." or short title → keep together
                                    current_title += ' ' + separator + ' ' + next_part
                                    i += 2
                            # NEW: Aggressive split mode for multiple "and"s
                            elif aggressive_split and next_word and next_word[0].isupper():
                                # Split every capitalized word
                                if current_title.strip():
                                    expanded_parts.append(current_title)
                                current_title = next_part
                                i += 2
                            # If current title already has "and"/"or" in it, and next is capitalized non-article
                            # then this is likely start of new title
                            elif (' and ' in current_title.lower() or ' or ' in current_title.lower()) and \
                                 next_word and next_word[0].isupper():
                                # Start new title
                                expanded_parts.append(current_title)
                                current_title = next_part
                                i += 2
                            else:
                                # Default: include in current title
                                current_title += ' ' + separator + ' ' + next_part
                                i += 2
                        else:
                            i += 1

                    # Add the last accumulated title
                    if current_title.strip():
                        expanded_parts.append(current_title)

            parts = expanded_parts
            for part in parts:
                clean = part.strip().strip('\'"')
                # Remove leading "and " or "or " if present
                clean = re.sub(r'^(?:and|or)\s+', '', clean, flags=re.IGNORECASE)

                # NEW: Clean up trailing question/recommendation phrases
                # Remove patterns like ". What other movies", ". Can you recommend", etc.
                clean = re.sub(r'[\.!?]\s+.*$', '', clean)  # Remove everything after punctuation
                clean = re.sub(r'\s+(?:what|can|could|would|should|do|recommend|suggest).*$', '', clean, flags=re.IGNORECASE)

                # Re-clean whitespace
                clean = clean.strip().strip('\'".,!?')
                clean = re.sub(r'\s+(?:please|pls|thanks|too|again)$', '', clean, flags=re.IGNORECASE)

                # Request words are not titles ("recommend something", "what else", "please")
                if re.match(r'^(?:what|which|how|recommend\w*|suggest\w*|can|could|would|please|something|'
                            r'anything|some|more|else)(?:\s|$)', clean, re.IGNORECASE):
                    continue

                # Filter out noise words and duplicates
                # NEW: Also filter single-word titles that are likely articles or fragments
                word_count = len(clean.split())
                is_likely_fragment = (word_count == 1 and clean.lower() in ['la', 'le', 'the', 'a', 'an', 'de', 'el'])

                if (clean and
                    clean.lower() not in ['it', 'that', 'this', 'them', 'what', 'can', 'you'] and
                    not is_likely_fragment and
                    len(clean) > 1 and
                    clean not in titles):
                    titles.append(clean)

            # If we found titles with this pattern, we're done with trigger patterns
            # (but we already have quoted titles, so only break if we didn't find any quotes)
            if titles and not (double_quoted or single_quoted):
                break

    # If we found quoted titles, only return those (ignore trigger pattern results)
    # This prevents duplicate/malformed entries
    if double_quoted or single_quoted:
        return titles[:len(double_quoted) + len(single_quoted)]

    return titles


def is_actor_query(text: str) -> bool:
    """
    Detect if the question is asking for RECOMMENDATIONS with a specific actor.
    Only matches recommendation-style queries (provide/recommend/suggest).
    Factual queries like "Which movies did X act in?" should go to factual QA pipeline.
    """
    patterns = [
        # Recommendation-style queries (provide/recommend/suggest/give me movies WITH actor)
        r'\b(?:recommend|suggest|provide|give\s+me)\s+(?:some\s+)?(?:movies?|films?)\s+(?:with|starring|featuring)',
        r'\b(?:movies?|films?)\s+(?:with|starring|featuring)\s+[A-Z]',  # "movies with Tom Hanks"
        r'\b(?:list|show)\s+(?:some\s+)?(?:movies?|films?)\s+(?:with|starring|that have)\s+',
        r'\bfilmography\b',  # Match "filmography" anywhere
    ]

    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def extract_actor_name(text: str) -> str:
    """
    Extract actor name from RECOMMENDATION queries like "movies with Tom Hanks" or "recommend films starring Brad Pitt".
    Only extracts from recommendation-style queries, not factual questions.
    """
    patterns = [
        # Pattern: "recommend/suggest/provide movies with/starring/featuring [Name]"
        r'(?:recommend|suggest|provide|give\s+me)\s+(?:some\s+)?(?:movies?|films?)\s+(?:with|starring|featuring)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',
        # Pattern: "movies with/starring/featuring [Name]"
        r'(?:movies?|films?)\s+(?:with|starring|featuring)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',
        # Pattern: "filmography of [Name]" or "[Name] filmography"
        r'filmography\s+of\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',
        r'([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\s+filmography',
        # Pattern: "show/list movies with/starring [Name]" (recommendation-style)
        r'(?:list|show)\s+(?:me\s+)?(?:some\s+)?(?:movies?|films?)\s+(?:with|starring|that have)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            # Clean up - remove trailing question marks, punctuation
            name = re.sub(r'[?\.,!]+$', '', name)
            return name

    return None


def get_movies_by_actor(graph, actor_name: str) -> List[Tuple[str, rdflib.URIRef]]:
    """
    Find all movies where the specified actor appeared.
    Returns list of (movie_label, movie_uri) tuples.
    """
    # First, find the actor's URI by searching labels (general entity resolution)
    actor_name_lower = actor_name.lower().strip()
    actor_uri = None

    for s, o in graph.subject_objects(RDFS.label):
        if isinstance(o, rdflib.Literal):
            label = str(o).lower().strip()
            if label == actor_name_lower:
                # Found exact match - use this as actor URI
                actor_uri = s
                break

    if not actor_uri:
        print(f"[recommender] Could not resolve actor: {actor_name}")
        return []

    # P161 is "cast member" - we need to find movies where actor_uri is the object
    cast_property = rdflib.URIRef('http://www.wikidata.org/prop/direct/P161')
    film_type = rdflib.URIRef('http://www.wikidata.org/entity/Q11424')
    instance_of = rdflib.URIRef('http://www.wikidata.org/prop/direct/P31')

    movies = []

    # Find all movies (subjects) that have this actor as cast member
    for movie_uri in graph.subjects(cast_property, actor_uri):
        # Verify it's actually a film
        if (movie_uri, instance_of, film_type) in graph:
            # Get movie label
            label = None
            for obj in graph.objects(movie_uri, RDFS.label):
                label = str(obj)
                break

            if label:
                movies.append((label, movie_uri))

    return movies


def extract_constraints(text: str) -> Dict[str, any]:
    """
    Extract filtering constraints from the query text.
    Returns a dict with constraint types and their values.

    Supported constraints:
    - rating_min: minimum rating (e.g., "rated above 7.5", "rating > 8.0")
    - rating_max: maximum rating (e.g., "rated below 9.0", "rating < 9.0")
    - rating_range: tuple of (min, max) (e.g., "rated between 7.5 and 9.0")
    - genres: list of genre names (e.g., "fantasy adventure films", "horror movies")
    """
    constraints = {}

    # Pattern 1: Rating range - "rated between X and Y" or "rating between X and Y"
    range_patterns = [
        r'rat(?:ed|ing)\s+between\s+(\d+(?:\.\d+)?)\s+and\s+(\d+(?:\.\d+)?)',
        r'between\s+(\d+(?:\.\d+)?)\s+and\s+(\d+(?:\.\d+)?)\s+(?:rating|stars?)',
        r'from\s+(\d+(?:\.\d+)?)\s+to\s+(\d+(?:\.\d+)?)\s+(?:rating|stars?)',
    ]

    for pattern in range_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            min_rating = float(match.group(1))
            max_rating = float(match.group(2))
            constraints['rating_range'] = (min_rating, max_rating)
            break

    # Pattern 2: Minimum rating - "rated above X", "rating > X", "at least X stars"
    if 'rating_range' not in constraints:
        min_patterns = [
            r'rat(?:ed|ing)\s+(?:above|over|greater\s+than)\s+(\d+(?:\.\d+)?)',
            r'rat(?:ed|ing)\s*[>≥]\s*(\d+(?:\.\d+)?)',
            r'at\s+least\s+(\d+(?:\.\d+)?)\s+(?:rating|stars?)',
            r'minimum\s+(?:rating|score)\s+of\s+(\d+(?:\.\d+)?)',
        ]

        for pattern in min_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                constraints['rating_min'] = float(match.group(1))
                break

    # Pattern 3: Maximum rating - "rated below X", "rating < X"
    if 'rating_range' not in constraints:
        max_patterns = [
            r'rat(?:ed|ing)\s+(?:below|under|less\s+than)\s+(\d+(?:\.\d+)?)',
            r'rat(?:ed|ing)\s*[<≤]\s*(\d+(?:\.\d+)?)',
            r'maximum\s+(?:rating|score)\s+of\s+(\d+(?:\.\d+)?)',
        ]

        for pattern in max_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                constraints['rating_max'] = float(match.group(1))
                break

    # Pattern 4: Genre extraction
    # Common genres with variations
    genre_keywords = {
        'action': ['action'],
        'adventure': ['adventure'],
        'comedy': ['comedy', 'comedies'],
        'drama': ['drama'],
        'horror': ['horror'],
        'thriller': ['thriller'],
        'romance': ['romance', 'romantic'],
        'sci-fi': ['sci-fi', 'science fiction', 'scifi'],
        'fantasy': ['fantasy'],
        'animation': ['animated', 'animation'],
        'documentary': ['documentary', 'documentaries'],
        'crime': ['crime'],
        'mystery': ['mystery'],
        'war': ['war'],
        'western': ['western'],
        'musical': ['musical'],
        'biography': ['biography', 'biographical', 'biopic'],
    }

    detected_genres = []
    text_lower = text.lower()

    for genre_name, keywords in genre_keywords.items():
        for keyword in keywords:
            if re.search(r'\b' + re.escape(keyword) + r'\b', text_lower):
                detected_genres.append(genre_name)
                break

    if detected_genres:
        constraints['genres'] = detected_genres

    return constraints


def detect_language_based_recommendation(text: str) -> Optional[Dict[str, str]]:
    """
    Detect if this is a language-based pseudo-recommendation.
    Examples:
      - "recommend Japanese action movies"
        -> {"language": "Japanese", "language_qid": "Q5287", "genre": "action"}
      - "suggest Turkish romantic comedies"
        -> {"language": "Turkish", "language_qid": "Q256", "genre": "romantic"}

    Returns:
      Dict with 'language', 'language_qid', and optional 'genre', or None if not this pattern.
    """
    # Language keywords mapping to Wikidata QIDs
    language_map = {
        'japanese': ('Japanese', 'Q5287'),
        'turkish': ('Turkish', 'Q256'),
        'french': ('French', 'Q150'),
        'german': ('German', 'Q188'),
        'spanish': ('Spanish', 'Q1321'),
        'italian': ('Italian', 'Q652'),
        'korean': ('Korean', 'Q9176'),
        'chinese': ('Chinese', 'Q7850'),
        'mandarin': ('Chinese', 'Q7850'),
        'hindi': ('Hindi', 'Q1568'),
        'arabic': ('Arabic', 'Q13955'),
        'russian': ('Russian', 'Q7737'),
        'portuguese': ('Portuguese', 'Q5146'),
        'english': ('English', 'Q1860'),
    }

    # Genre keywords (same as before)
    genre_keywords = ['biographical', 'biography', 'action', 'comedy', 'drama', 'horror',
                      'thriller', 'romance', 'romantic', 'sci-fi', 'fantasy', 'documentary',
                      'animated', 'musical', 'western', 'crime', 'mystery']

    patterns = [
        # "recommend Japanese action movies", "suggest Turkish romantic comedies", "recommend Korean dramas"
        r'(?:recommend|suggest)\s+(?:some\s+)?(?:good\s+)?([A-Z][a-z]+)\s+(.*?)(?:movie|film|drama|thriller|comedi)',

        # "I want Japanese action films"
        r'I\s+(?:want|need)\s+([A-Z][a-z]+)\s+(.*?)(?:movie|film|drama)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            first_word = match.group(1)
            genre_part = match.group(2).strip() if match.group(2) else ""

            # Check if first word is a language
            if first_word.lower() in language_map:
                lang_name, lang_qid = language_map[first_word.lower()]
                result = {'language': lang_name, 'language_qid': lang_qid}

                # Check if genre_part contains genre keywords
                # Support multi-word genres like "romantic comedy"
                genre_part_lower = genre_part.lower()
                for keyword in genre_keywords:
                    if keyword in genre_part_lower:
                        result['genre'] = keyword
                        break

                return result

    # Fallback: capture "movies in Japanese" or "Japanese movies" questions (including "do you recommend")
    lowered = text.lower()
    if re.search(r'\b(?:recommend|suggest|what\s+.*(?:watch|see))', lowered):
        for lang_key, (lang_name, lang_qid) in language_map.items():
            pattern_forward = rf'\b(?:movies?|films?)\s+(?:in\s+)?{lang_key}\b'
            pattern_reverse = rf'\b{lang_key}\b[^\.?!]*\b(?:movies?|films?)'
            if re.search(pattern_forward, lowered) or re.search(pattern_reverse, lowered):
                result = {'language': lang_name, 'language_qid': lang_qid}
                for keyword in genre_keywords:
                    if keyword in lowered:
                        result['genre'] = keyword
                        break
                return result

    return None


def detect_person_based_recommendation(text: str, person_type: str) -> Optional[Dict[str, str]]:
    """
    Detect if this is a pseudo-recommendation based on a person (actor/director/composer/screenwriter).

    Examples:
      - "recommend biographical movies given that I like Meryl Streep" (actor)
      - "suggest films since I love Christopher Nolan" (director)
      - "recommend movies because I enjoy Hans Zimmer's music" (composer)

    Args:
        text: Query text
        person_type: One of 'actor', 'director', 'composer', 'screenwriter'

    Returns:
        Dict with person name and optional 'genre', or None if not this pattern.
    """
    # Extended patterns covering more variations
    # For composers/writers/directors/actors, we need explicit relationship patterns too
    explicit_patterns = {
        'actor': [
            r'(?:movies?|films?)\s+(?:starring|featuring)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',
            r'(?:movies?|films?)\s+with\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\s+(?:in\s+(?:the\s+)?(?:cast|starring\s+role))',
        ],
        'director': [
            r'(?:movies?|films?)\s+directed\s+by\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',
            r'(?:movies?|films?)\s+(?:from|by)\s+director\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',
        ],
        'composer': [
            r'(?:movies?|films?)\s+with\s+(?:music|score|soundtrack)\s+by\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',
            r'(?:movies?|films?)\s+(?:scored|composed)\s+by\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',
        ],
        'screenwriter': [
            r'(?:movies?|films?)\s+written\s+by\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',
            r'(?:movies?|films?)\s+(?:from|by)\s+(?:writer|screenwriter)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',
        ],
    }

    # Check explicit patterns first (they take priority)
    if person_type in explicit_patterns:
        for pattern in explicit_patterns[person_type]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result = {'type': person_type, 'name': match.group(1).strip()}
                # Check for genre in full text
                genre_keywords = ['biographical', 'action', 'comedy', 'drama', 'horror',
                                  'thriller', 'romance', 'sci-fi', 'fantasy', 'documentary',
                                  'animated', 'musical', 'western', 'crime', 'mystery']
                for genre in genre_keywords:
                    if genre in text.lower():
                        result['genre'] = genre
                        break
                return result

    # General patterns (for "I like X, recommend movies" style)
    patterns = [
        # Pattern 1: "recommend X movies given that/since/because I like/love/enjoy [PERSON]"
        r'(?:recommend|suggest|give\s+me)\s+(?:some\s+)?(?:good\s+)?([A-Za-z\-]+)\s+(?:movies?|films?)\s+(?:given\s+that|since|because|as)\s+I\s+(?:like|love|enjoy|am\s+a\s+fan\s+of)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',

        # Pattern 2: "recommend movies given that I like [PERSON]" (genre extracted separately)
        r'(?:recommend|suggest|give\s+me)\s+(?:some\s+)?(?:good\s+)?(?:movies?|films?)\s+(?:given\s+that|since|because|as)\s+I\s+(?:like|love|enjoy|am\s+a\s+fan\s+of)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',

        # Pattern 3: "I like [PERSON], recommend X movies"
        r'I\s+(?:like|love|enjoy|am\s+a\s+fan\s+of)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*),?\s+(?:recommend|suggest|give\s+me)\s+(?:some\s+)?(?:good\s+)?([A-Za-z\-]+)?\s*(?:movies?|films?)',

        # Pattern 4: "I like [PERSON], recommend some movies" (no genre)
        r'I\s+(?:like|love|enjoy|am\s+a\s+fan\s+of)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*),?\s+(?:recommend|suggest|give\s+me)',

        # Pattern 5: "since I'm into [PERSON], recommend movies"
        r'(?:since|given\s+that|because|as)\s+I(?:\'m|\s+am)\s+(?:into|a\s+fan\s+of)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*),?\s+(?:recommend|suggest)',

        # Pattern 6: "recommend movies for someone who likes [PERSON]"
        r'(?:recommend|suggest)\s+(?:movies?|films?)\s+for\s+(?:someone|people)\s+who\s+(?:like|love|enjoy)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',

        # Pattern 7: "what movies should I watch if I like [PERSON]"
        r'what\s+(?:movies?|films?)\s+should\s+I\s+(?:watch|see)\s+if\s+I\s+(?:like|love|enjoy)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            groups = match.groups()
            result = {'type': person_type}

            # Determine which group is person name vs genre
            if len(groups) == 2:
                first = groups[0] if groups[0] else ""
                second = groups[1] if groups[1] else ""

                # Genre keywords (lowercase)
                genre_keywords = ['biographical', 'action', 'comedy', 'drama', 'horror',
                                  'thriller', 'romance', 'sci-fi', 'fantasy', 'documentary',
                                  'animated', 'musical', 'western', 'crime', 'mystery']

                if first.lower() in genre_keywords:
                    result['genre'] = first
                    result['name'] = second
                elif second and second[0].isupper():  # Capitalized = likely person name
                    result['name'] = second
                    if first and first.lower() in genre_keywords:
                        result['genre'] = first
            elif len(groups) == 1:
                # Only person name captured
                result['name'] = groups[0]

            if 'name' in result and result['name']:
                return result

    return None


def detect_actor_based_recommendation(text: str) -> Optional[Dict[str, str]]:
    """
    Detect if this is a pseudo-recommendation based on an actor.
    Examples:
      - "recommend biographical movies given that I like Meryl Streep"
        -> {"actor": "Meryl Streep", "genre": "biographical"}
      - "suggest some action films since I love Tom Cruise"
        -> {"actor": "Tom Cruise", "genre": "action"}

    Returns:
      Dict with 'actor' and optional 'genre', or None if not this pattern.
    """
    result = detect_person_based_recommendation(text, 'actor')
    if result:
        result['actor'] = result.pop('name')
        result.pop('type')
    return result


def detect_director_based_recommendation(text: str) -> Optional[Dict[str, str]]:
    """
    Detect if this is a pseudo-recommendation based on a director.
    Examples:
      - "recommend movies given that I like Christopher Nolan"
      - "suggest films since I love Quentin Tarantino"

    Returns:
      Dict with 'director' and optional 'genre', or None if not this pattern.
    """
    # Check for director-specific keywords - only proceed if found
    director_indicators = [
        r'\bdirect(?:or|ed|ed by|ing)\b',
        r'\bfilmmaker\b',
        r'\bhelm(?:ed|er)?\b',
        r"(?:Nolan|Tarantino|Spielberg|Scorsese|Fincher|Anderson|Kubrick|Hitchcock|Coppola|Lynch|Burton|Cameron|Scott|Bay|Jackson)",  # Common directors
    ]

    has_director_indicator = any(re.search(pattern, text, re.IGNORECASE) for pattern in director_indicators)

    if not has_director_indicator:
        return None

    result = detect_person_based_recommendation(text, 'director')
    if result:
        result['director'] = result.pop('name')
        result.pop('type')
        return result
    return None


def detect_composer_based_recommendation(text: str) -> Optional[Dict[str, str]]:
    """
    Detect if this is a pseudo-recommendation based on a composer.
    Examples:
      - "recommend movies because I enjoy Hans Zimmer's music"
      - "suggest films with music by John Williams"

    Returns:
      Dict with 'composer' and optional 'genre', or None if not this pattern.
    """
    # Check for composer-specific keywords - only proceed if found
    composer_indicators = [
        r'\bcompos(?:er|ed|es)\b',
        r'\bmusic(?:\s+by)?\b',
        r'\bscore(?:\s+by)?\b',
        r'\bsoundtrack\b',
        r"(?:Zimmer|Williams|Morricone|Elfman|Shore|Giacchino|Desplat|Newman|Silvestri|Horner|Goldsmith)",  # Common composers
    ]

    has_composer_indicator = any(re.search(pattern, text, re.IGNORECASE) for pattern in composer_indicators)

    if not has_composer_indicator:
        return None

    result = detect_person_based_recommendation(text, 'composer')
    if result:
        result['composer'] = result.pop('name')
        result.pop('type')
        return result
    return None


def detect_screenwriter_based_recommendation(text: str) -> Optional[Dict[str, str]]:
    """
    Detect if this is a pseudo-recommendation based on a screenwriter.
    Examples:
      - "recommend movies written by Aaron Sorkin"
      - "suggest films since I like Charlie Kaufman's writing"

    Returns:
      Dict with 'screenwriter' and optional 'genre', or None if not this pattern.
    """
    # Check for screenwriter-specific keywords - only proceed if found
    writer_indicators = [
        r'\bwrit(?:er|ten|ing|e)\b',
        r'\bscreenplay\b',
        r'\bscreenwriter\b',
        r'\bscript\b',
        r"(?:Sorkin|Kaufman|Goldman|Towne|Mamet|Chazelle|McDonagh|Tarantino|Anderson|Allen)",  # Common writers (some also direct)
    ]

    has_writer_indicator = any(re.search(pattern, text, re.IGNORECASE) for pattern in writer_indicators)

    if not has_writer_indicator:
        return None

    result = detect_person_based_recommendation(text, 'screenwriter')
    if result:
        result['screenwriter'] = result.pop('name')
        result.pop('type')
        return result
    return None


def detect_production_company_based_recommendation(text: str) -> Optional[Dict[str, str]]:
    """
    Detect if this is a pseudo-recommendation based on a production company.
    Examples:
      - "recommend movies since I love Pixar films"
      - "suggest films because I enjoy Disney productions"

    Returns:
      Dict with 'company' and optional 'genre', or None if not this pattern.
    """
    # Production company mappings
    company_keywords = {
        'disney': 'Walt Disney Pictures',
        'pixar': 'Pixar',
        'marvel': 'Marvel Studios',
        'dc': 'DC Films',
        'paramount': 'Paramount Pictures',
        'warner': 'Warner Bros.',
        'warner bros': 'Warner Bros.',
        'universal': 'Universal Pictures',
        'sony': 'Sony Pictures',
        'fox': '20th Century Fox',
        '20th century': '20th Century Fox',
        'dreamworks': 'DreamWorks Pictures',
        'mgm': 'Metro-Goldwyn-Mayer',
        'lionsgate': 'Lionsgate Films',
        'columbia': 'Columbia Pictures',
        'a24': 'A24',
        'miramax': 'Miramax',
        'ghibli': 'Studio Ghibli',
        'studio ghibli': 'Studio Ghibli',
    }

    patterns = [
        # "recommend movies since I love [COMPANY] films"
        r'(?:recommend|suggest|give\s+me)\s+(?:some\s+)?(?:movies?|films?)\s+(?:since|because|given\s+that|as)\s+I\s+(?:love|like|enjoy)\s+([A-Za-z0-9\s]+)\s+(?:films?|movies?|productions?)',

        # "I love [COMPANY], recommend movies"
        r'I\s+(?:love|like|enjoy)\s+([A-Za-z0-9\s]+),?\s+(?:recommend|suggest)',

        # "recommend [COMPANY] movies"
        r'(?:recommend|suggest)\s+(?:some\s+)?([A-Za-z0-9\s]+)\s+(?:films?|movies?)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            company_text = match.group(1).strip().lower()

            # Check if it matches a known company
            for keyword, company_name in company_keywords.items():
                if keyword in company_text:
                    result = {'company': company_name}

                    # Check for genre in the text
                    genre_keywords = ['action', 'comedy', 'drama', 'horror', 'thriller',
                                      'romance', 'animated', 'documentary']
                    for genre in genre_keywords:
                        if genre in text.lower():
                            result['genre'] = genre
                            break

                    return result

    return None


def is_recommendation_question(text: str) -> bool:
    """
    Detect if the question is explicitly asking for movie RECOMMENDATIONS.
    Must be very strict to avoid catching factual questions.
    Only matches queries that are clearly requesting movie suggestions.
    """
    # NEW: Check if this is a pseudo-recommendation (factual query in disguise)
    # These should be treated as factual queries, not recommendations
    if detect_actor_based_recommendation(text):
        return False  # Treat as factual query, not recommendation
    if detect_director_based_recommendation(text):
        return False
    if detect_composer_based_recommendation(text):
        return False
    if detect_screenwriter_based_recommendation(text):
        return False
    if detect_production_company_based_recommendation(text):
        return False

    # Language-based queries are only treated as factual if there are NO seed titles
    # If there are seed titles, it's a proper recommendation with language constraint
    if detect_language_based_recommendation(text):
        seed_titles = extract_movie_titles(text)
        if not seed_titles:
            return False  # No seeds = factual query (e.g., "What German movies exist?")
        # Has seeds = recommendation with language constraint (e.g., "Like Frozen, recommend German movies")

    # First, exclude factual question words that indicate NOT a recommendation
    factual_indicators = [
        r'\b(?:who|when|where|why|how)\b',  # WH-questions are usually factual
        r'\b(?:director|cast|actor|actress|writer|producer|star)\b',  # Asking about people
        r'\b(?:award|oscar|nomination|prize|won|winner)\b',  # Awards questions
        r'\b(?:budget|box\s+office|revenue|gross|profit)\b',  # Financial questions
        r'\b(?:rating|score|review|critic)\b',  # Review questions
        r'\b(?:release|premiere|date|year)\b',  # Date questions
        r'\b(?:plot|story|about|summary|synopsis)\b',  # Plot questions
        r'\b(?:genre|length|runtime|duration)\b',  # Metadata questions
        r'\b(?:soundtrack|music|score|composer)\b',  # Music questions
        r'\b(?:filmed|shot|location|setting)\b',  # Production questions
    ]

    # Titles named as seeds ("movies like Star Wars", "similar to The Score") must not trip the
    # factual indicators below, so they are blanked out before the check.
    check_text = text
    for title in extract_movie_titles(text):
        check_text = re.sub(re.escape(title), " ", check_text, flags=re.IGNORECASE)

    for indicator in factual_indicators:
        if re.search(indicator, check_text, re.IGNORECASE):
            return False  # This is likely a factual question, not a recommendation

    # Now check for explicit recommendation patterns
    patterns = [
        # Direct recommendation verbs (must be followed by movie/film words)
        r'\b(?:recommend|suggest)\s+(?:me\s+)?(?:some\s+)?(?:good\s+)?(?:movies?|films?)',
        r'\b(?:recommend|suggest)\b.*\b(?:movies?|films?)',
        r'\b(?:give|show|provide|list)\s+(?:me\s+)?(?:some\s+)?(?:good\s+)?(?:[\w\-]+\s+)*?(?:movies?|films?)',
        # Phrasings where the noun comes first: "movies ... do you recommend"
        r'\b(?:movies?|films?)\b.*?\b(?:recommend|suggest)\b',

        # Similar/like patterns (clear recommendation intent)
        r'\b(?:similar|like)\s+(?:to\s+)?.*(?:recommend|suggest)',
        r'\b(?:movies?|films?)\s+(?:like|similar\s+to)\s+',
        r'\bsimilar\s+to\b.*\b(?:movies?|films?)',

        # "What should I watch" patterns
        r'\bwhat\s+should\s+I\s+(?:watch|see)',
        r'\bwhat\s+(?:movie|film)\s+should\s+I\s+(?:watch|see)',
        r'\bwhat\s+(?:[\w\-]+\s+)*?(?:movies?|films?).*?\s+should\s+I\s+(?:watch|see)',
        r'\bwhat\s+(?:[\w\-]+\s+)*?(?:movies?|films?).*?\s+(?:can|could|would)\s+I\s+(?:watch|see)',
        r'\bwhat\s+to\s+(?:watch|see)',

        # Mood/preference patterns
        r'\bin\s+the\s+mood\s+for\s+.*\b(?:movies?|films?)',
        r'\bfeel\s+like\s+watching\b',
        r'\bwant\s+to\s+watch\b.*\b(?:like|similar)',
        r'\blooking\s+for\s+(?:movies?|films?)\s+(?:like|similar)',
        r'\bany\s+(?:[\w\-]+\s+)*?(?:movies?|films?)',

        # Personal taste leading to recommendation
        r'^I\s+(?:love|loved|enjoy|enjoyed|like|liked)\s+.*(?:recommend|suggest|similar|what\s+else)',
        r'^I\s+watched\s+.*(?:what\s+else|similar|recommend|suggest)',

        # Direct need/provide phrasing
        r'\bneed\s+(?:a|some)\s+.*\b(?:movies?|films?|horror|slasher|comedy|drama|thriller|romcom|musical|documentary)\b',
        r'\bany\s+.*\b(?:movies?|films?)\b',

        # Any wording of "similar" or a recommendation noun/verb, with or without a film word:
        # "Similar movies to Chicken Little", "Chicken Little similar", "something like Up",
        # "any recommendations similar to Toy Story?", "recommend me a comedy"
        r'\b(?:similar|alike|lookalikes?)\b',
        r'\b(?:something|anything|more|others?|ones?|stuff)\s+(?:like|similar)\b',
        r'\b(?:recommend|suggest)\w*\b',
        r'[\s\-]like\s+(?:movies?|films?)\b',
        r'\b(?:watch|see)\s+(?:next\s+)?(?:after|following)\b',
        r'\bafter\s+(?:watching|seeing)\b',
    ]

    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True  # This is a recommendation request

    return False  # Default: not a recommendation


def _is_film_entity(graph, entity_uri) -> bool:
    """
    Check if an entity is a film or film-related type.
    Accepts: Q11424 (film), Q202866 (animated film), and other film subtypes.
    """
    p31_uri = rdflib.URIRef('http://www.wikidata.org/prop/direct/P31')

    # Accepted film types
    film_types = [
        rdflib.URIRef('http://www.wikidata.org/entity/Q11424'),    # film
        rdflib.URIRef('http://www.wikidata.org/entity/Q202866'),   # animated film
        rdflib.URIRef('http://www.wikidata.org/entity/Q24869'),    # feature film
        rdflib.URIRef('http://www.wikidata.org/entity/Q506240'),   # short film
        rdflib.URIRef('http://www.wikidata.org/entity/Q157443'),   # comedy film
        rdflib.URIRef('http://www.wikidata.org/entity/Q130232'),   # drama film
        rdflib.URIRef('http://www.wikidata.org/entity/Q200092'),   # horror film
        rdflib.URIRef('http://www.wikidata.org/entity/Q188473'),   # action film
        rdflib.URIRef('http://www.wikidata.org/entity/Q2484376'),  # thriller film
    ]

    # Check if entity has any of these film types
    for film_type in film_types:
        if (entity_uri, p31_uri, film_type) in graph:
            return True

    return False


def resolve_movie_uri(graph, title: str) -> rdflib.URIRef:
    """
    Resolve a movie title to its URI in the graph.
    Prioritizes exact matches and checks if it's actually a movie (includes animated films, etc.).
    When multiple films match, prioritizes by rating (highest rated film).
    """
    from core.data import load_ratings

    title_lower = title.lower().strip()

    # First pass: look for exact matches
    exact_matches = []
    partial_matches = []

    for s, o in graph.subject_objects(RDFS.label):
        if isinstance(o, rdflib.Literal):
            label = str(o)
            label_lower = label.lower().strip()

            if label_lower == title_lower:
                exact_matches.append(s)
            elif title_lower in label_lower or label_lower in title_lower:
                partial_matches.append(s)

    # Check if any exact match is a movie and collect all film candidates
    # First, collect exact film matches
    exact_film_matches = []
    for candidate in exact_matches:
        # Check if it's a film (using expanded film type check)
        if _is_film_entity(graph, candidate):
            exact_film_matches.append(candidate)

    # ALWAYS check article variants too (not just when no exact matches)
    # For example: "Godfather" should also consider "The Godfather"
    # This allows rating-based prioritization between them
    article_variants = [
        f"the {title_lower}",
        f"a {title_lower}",
        f"an {title_lower}",
    ]

    for variant in article_variants:
        for s, o in graph.subject_objects(RDFS.label):
            if isinstance(o, rdflib.Literal):
                label_lower = str(o).lower().strip()
                if label_lower == variant:
                    if _is_film_entity(graph, s):
                        # Avoid duplicates
                        if s not in exact_film_matches:
                            exact_film_matches.append(s)

    # If we have multiple exact film matches (including article variants),
    # prioritize by rating (highest first)
    if len(exact_film_matches) > 1:
        ratings = load_ratings(use_cache=True)
        exact_film_matches.sort(key=lambda uri: ratings.get(str(uri), 0.0), reverse=True)

    if exact_film_matches:
        return exact_film_matches[0]

    # If no exact matches found, try partial matches (but with rating prioritization)
    partial_film_matches = []
    for candidate in partial_matches:
        if _is_film_entity(graph, candidate):
            partial_film_matches.append(candidate)

    if len(partial_film_matches) > 1:
        ratings = load_ratings(use_cache=True)
        partial_film_matches.sort(key=lambda uri: ratings.get(str(uri), 0.0), reverse=True)

    if partial_film_matches:
        return partial_film_matches[0]

    # Return first exact match even if not confirmed as film
    if exact_matches:
        return exact_matches[0]

    # Last resort: return first partial match
    if partial_matches:
        return partial_matches[0]

    return None


def get_movie_properties(graph, movie_uri: rdflib.URIRef) -> Dict[str, Set]:
    """
    Extract key properties of a movie from the graph.
    Returns a dict with sets of property values: genre, director, screenwriter, etc.
    """
    properties = {
        'genre': set(),               # P136
        'director': set(),            # P57
        'screenwriter': set(),        # P58
        'composer': set(),            # P86
        'country': set(),             # P495
        'cast': set(),                # P161
        'production_company': set(),  # P272
        'producer': set(),            # P162
        'cinematographer': set(),     # P344 (director of photography)
        'original_language': set(),   # P364
        'costume_designer': set(),    # P2515 (costume designer)
    }

    property_uris = {
        'genre': 'http://www.wikidata.org/prop/direct/P136',
        'director': 'http://www.wikidata.org/prop/direct/P57',
        'screenwriter': 'http://www.wikidata.org/prop/direct/P58',
        'composer': 'http://www.wikidata.org/prop/direct/P86',
        'country': 'http://www.wikidata.org/prop/direct/P495',
        'cast': 'http://www.wikidata.org/prop/direct/P161',
        'production_company': 'http://www.wikidata.org/prop/direct/P272',
        'producer': 'http://www.wikidata.org/prop/direct/P162',
        'cinematographer': 'http://www.wikidata.org/prop/direct/P344',
        'original_language': 'http://www.wikidata.org/prop/direct/P364',
        'costume_designer': 'http://www.wikidata.org/prop/direct/P2515',
    }

    for prop_name, prop_uri in property_uris.items():
        prop_ref = rdflib.URIRef(prop_uri)
        for obj in graph.objects(movie_uri, prop_ref):
            properties[prop_name].add(str(obj))

    return properties


_SIM_WEIGHTS = {
    # Genre and the people who shape a film carry the signal; a shared composer or costume
    # designer alone (one name across very different films) must not decide the match.
    'genre': 5.0,
    'director': 3.5,
    'screenwriter': 2.5,
    'production_company': 2.5,
    'cast': 2.5,
    'composer': 1.2,
    'producer': 1.2,
    'costume_designer': 0.8,
    'cinematographer': 0.8,
    'country': 0.4,
    'original_language': 0.4,
}


def _facet_similarity(prop_name: str, set1: Set, set2: Set) -> float:
    """Similarity of one facet in [0, 1]."""
    inter = len(set1 & set2)
    if not inter:
        return 0.0
    if prop_name == 'genre':
        # Jaccard, lifted so that sharing half the genres already counts as a strong match
        return min(1.0, 1.6 * inter / len(set1 | set2))
    if prop_name == 'cast':
        # casts are long: three shared actors is a full match
        return min(1.0, inter / 3)
    # one shared director/writer/studio is a strong signal whatever the list lengths
    return inter / min(len(set1), len(set2))


def calculate_similarity(props1: Dict[str, Set], props2: Dict[str, Set]) -> float:
    """
    Weighted facet similarity between a seed (props1) and a candidate (props2), in [0, 1].

    The score is normalised by the weight of every facet the SEED has, so a candidate that
    shares one rare facet (e.g. only the composer) and nothing else scores low instead of
    being judged on that facet alone.
    """
    total_score = 0.0
    total_weight = 0.0
    for prop_name, weight in _SIM_WEIGHTS.items():
        set1 = props1.get(prop_name, set())
        if not set1:
            continue
        total_weight += weight
        set2 = props2.get(prop_name, set())
        if set2:
            total_score += weight * _facet_similarity(prop_name, set1, set2)
    if total_weight == 0:
        return 0.0
    return min(total_score / total_weight, 1.0)


def _count_property_overlap(props1: Dict[str, Set], props2: Dict[str, Set]) -> int:
    """Return how many high-signal property types overlap."""
    key_props = (
        'genre',
        'director',
        'screenwriter',
        'composer',
        'production_company',
        'cast',
    )
    overlap = 0
    for prop in key_props:
        set1 = props1.get(prop)
        set2 = props2.get(prop)
        if set1 and set2 and (set1 & set2):
            overlap += 1
    return overlap


def recommend_movies_by_actor(graph, actor_name: str, top_k: int = 5) -> List[Tuple[str, float]]:
    """
    Recommend movies based on an actor's filmography.
    Finds movies where the actor appeared, analyzes their properties,
    and recommends similar movies.

    Args:
        graph: The RDF graph
        actor_name: Name of the actor (e.g., "Tom Hanks")
        top_k: Number of recommendations to return

    Returns:
        List of (movie_label, similarity_score) tuples
    """
    # Get all movies this actor appeared in
    actor_movies = get_movies_by_actor(graph, actor_name)

    if not actor_movies:
        print(f"[recommender] No movies found for actor: {actor_name}")
        return []

    print(f"[recommender] Found {len(actor_movies)} movies for {actor_name}")

    # Extract just the titles for recommendation
    seed_titles = [movie_label for movie_label, _ in actor_movies]

    # Use the regular recommendation system
    # But exclude the actor's own movies from recommendations
    actor_movie_uris = set(movie_uri for _, movie_uri in actor_movies)

    # Get recommendations based on the actor's movies
    # Use lenient genre filtering since actors have diverse filmographies
    recommendations = recommend_movies(graph, seed_titles, top_k * 2, lenient_genre_filter=True)  # Get more to filter

    # Filter out the actor's own movies
    filtered_recommendations = []
    for movie_label, score in recommendations:
        # Check if this movie is in the actor's filmography
        movie_uri = resolve_movie_uri(graph, movie_label)
        if movie_uri not in actor_movie_uris:
            filtered_recommendations.append((movie_label, score))
            if len(filtered_recommendations) >= top_k:
                break

    return filtered_recommendations


def get_movie_rating(graph, movie_uri: rdflib.URIRef) -> float:
    """
    Get the IMDb rating of a movie from the graph.
    Returns the rating as a float, or None if not found.
    """
    # P2487 is IMDb rating (value is typically out of 10)
    rating_property = rdflib.URIRef('http://www.wikidata.org/prop/direct/P2487')

    for rating_obj in graph.objects(movie_uri, rating_property):
        try:
            # Rating is stored as a string or decimal
            rating = float(str(rating_obj))
            return rating
        except (ValueError, TypeError):
            continue

    return None


def movie_matches_genre(graph, movie_uri: rdflib.URIRef, target_genres: List[str]) -> bool:
    """
    Check if a movie matches any of the target genres.
    Returns True if the movie has at least one matching genre.
    Uses genre synonyms for better matching.
    """
    if not target_genres:
        return True  # No genre constraint

    # Genre synonyms mapping for better matching
    genre_synonyms = {
        'action': ['action'],
        'adventure': ['adventure'],
        'comedy': ['comedy', 'comedies'],
        'drama': ['drama'],
        'horror': ['horror'],
        'thriller': ['thriller'],
        'romance': ['romance', 'romantic'],
        'sci-fi': ['sci-fi', 'science fiction', 'scifi', 'science-fiction'],
        'fantasy': ['fantasy'],
        'animation': ['animated', 'animation'],
        'documentary': ['documentary', 'documentaries'],
        'crime': ['crime'],
        'mystery': ['mystery'],
        'war': ['war'],
        'western': ['western'],
        'musical': ['musical'],
        'biography': ['biography', 'biographical', 'biopic'],
    }

    # Get movie genres
    genre_property = rdflib.URIRef('http://www.wikidata.org/prop/direct/P136')
    movie_genres = set()

    for genre_uri in graph.objects(movie_uri, genre_property):
        # Get genre label
        for label_obj in graph.objects(genre_uri, RDFS.label):
            genre_label = str(label_obj).lower()
            movie_genres.add(genre_label)

    # Check if any movie genre matches any target genre (with synonyms)
    for target_genre in target_genres:
        # Get synonyms for this target genre
        synonyms = genre_synonyms.get(target_genre.lower(), [target_genre.lower()])

        for synonym in synonyms:
            for movie_genre in movie_genres:
                if synonym in movie_genre or movie_genre in synonym:
                    return True

    return False


def movie_matches_language(graph, movie_uri: rdflib.URIRef, language_qid: str) -> bool:
    """Return True if movie has the requested original language."""
    if not language_qid:
        return True

    lang_prop = rdflib.URIRef('http://www.wikidata.org/prop/direct/P364')

    for lang_obj in graph.objects(movie_uri, lang_prop):
        lang_qid = _qid_from_uri(str(lang_obj))
        if lang_qid == language_qid:
            return True

    return False


def apply_constraints(graph, recommendations: List[Tuple[str, float]],
                     constraints: Dict[str, any]) -> List[Tuple[str, float]]:
    """
    Filter recommendations based on extracted constraints.

    Args:
        graph: The RDF graph
        recommendations: List of (movie_label, similarity_score) tuples
        constraints: Dict with constraint types and values

    Returns:
        Filtered list of (movie_label, similarity_score) tuples
    """
    if not constraints:
        return recommendations

    filtered = []

    for movie_label, score in recommendations:
        # Resolve movie URI
        movie_uri = resolve_movie_uri(graph, movie_label)
        if not movie_uri:
            continue

        # Check rating constraints (only if rating data is available)
        if 'rating_range' in constraints or 'rating_min' in constraints or 'rating_max' in constraints:
            rating = get_movie_rating(graph, movie_uri)
            if rating is not None:
                # Check rating range
                if 'rating_range' in constraints:
                    min_rating, max_rating = constraints['rating_range']
                    if not (min_rating <= rating <= max_rating):
                        continue
                else:
                    # Check min rating
                    if 'rating_min' in constraints and rating < constraints['rating_min']:
                        continue
                    # Check max rating
                    if 'rating_max' in constraints and rating > constraints['rating_max']:
                        continue
            # If rating is None, we don't skip - just can't filter by rating

        # Check genre constraints
        if 'genres' in constraints:
            if not movie_matches_genre(graph, movie_uri, constraints['genres']):
                continue

        # Language filter (original language P364)
        if 'language_qid' in constraints:
            if not movie_matches_language(graph, movie_uri, constraints['language_qid']):
                continue

        # All constraints passed
        filtered.append((movie_label, score))

    return filtered


def recommend_movies_with_constraints(graph, seed_titles: List[str],
                                     constraints: Dict[str, any] = None,
                                     top_k: int = 5) -> List[Tuple[str, float]]:
    """
    Recommend movies with optional filtering constraints.

    Args:
        graph: The RDF graph
        seed_titles: List of seed movie titles
        constraints: Dict with constraint types (rating, genre, etc.)
        top_k: Number of recommendations to return

    Returns:
        List of (movie_label, similarity_score) tuples
    """
    # Get more recommendations to compensate for filtering
    multiplier = 1
    if constraints:
        multiplier = 10
        if constraints.get('genres'):
            multiplier = max(multiplier, 12)
        if constraints.get('language_qid'):
            multiplier = max(multiplier, 18)
        initial_k = top_k * multiplier
    else:
        initial_k = top_k

    # Get initial recommendations
    recommendations = recommend_movies(graph, seed_titles, initial_k)

    # Apply constraints if any
    if constraints:
        print(f"[recommender] Applying constraints: {constraints}")
        recommendations = apply_constraints(graph, recommendations, constraints)

    # Return top K after filtering
    return recommendations[:top_k]


def recommend_movies(graph, seed_titles: List[str], top_k: int = 5, lenient_genre_filter: bool = False) -> List[Tuple[str, float]]:
    """
    Recommend movies based on a list of seed titles.
    Returns list of (movie_label, similarity_score) tuples.

    Args:
        graph: RDF graph
        seed_titles: List of seed movie titles
        top_k: Number of recommendations to return
        lenient_genre_filter: If True, use softer genre gating (useful for actor queries)
    """
    # 1. Resolve seed movie URIs (the entity linker when it is built: typo-tolerant, picks the
    #    well-known film among same-named ones; else the label scan)
    seed_uris = []
    seed_names = []
    for title in seed_titles:
        uris, name = _resolve_seeds(graph, title)
        if uris:
            seed_uris.extend(u for u in uris if u not in seed_uris)
            seed_names.append(name or title)
        else:
            print(f"[recommender] Could not resolve title: {title}")

    LAST_RUN['seeds'] = [str(u) for u in seed_uris]
    LAST_RUN['seed_names'] = seed_names
    LAST_RUN['recommendations'] = {}
    if not seed_uris:
        return []

    # 2. Get properties and embedding IDs of seed movies
    seed_profiles: List[MovieProfile] = []
    seed_embed_ids: List[int] = []
    seed_genre_union: Set[str] = set()

    for uri in seed_uris:
        profile = _get_movie_profile(graph, uri)
        seed_profiles.append(profile)
        seed_genre_union |= profile.properties.get('genre', set())

        if profile.embedding_id is not None:
            seed_embed_ids.append(profile.embedding_id)

    # Remakes and re-releases share the seed's title; recommending "The Lion King" for
    # "The Lion King" reads as an error, so same-titled films are left out.
    seed_labels = {p.label.lower() for p in seed_profiles if p.label}

    # 3. Find all movies in the graph (instances of Q11424 - film)
    candidate_movies = set()

    p31_uri = rdflib.URIRef('http://www.wikidata.org/prop/direct/P31')
    film_uri = rdflib.URIRef('http://www.wikidata.org/entity/Q11424')

    for s in graph.subjects(p31_uri, film_uri):
        if s not in seed_uris:  # Don't recommend seed movies
            candidate_movies.add(s)

    print(f"[recommender] Found {len(candidate_movies)} candidate movies")

    # 4. Calculate similarity for each candidate
    recommendations: List[Tuple[str, float, float, str]] = []
    seen_titles: Set[str] = set()

    for candidate_uri in candidate_movies:
        profile = _get_movie_profile(graph, candidate_uri)
        label = profile.label
        if not label or label.lower() in seen_titles or label.lower() in seed_labels:
            continue

        # Filter out suspicious labels (keeps dataset clean)
        word_count = len(label.split())
        if word_count > 8:
            continue
        words = label.split()
        if word_count >= 3:
            common_words = {'the', 'of', 'and', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'vol', 'part', 'reloaded', 'returns', 'ii', 'iii'}
            capitalized_uncommon = [w for w in words if w and w[0].isupper() and w.lower() not in common_words]
            if len(capitalized_uncommon) == word_count and not any(w.lower() in common_words for w in words):
                continue

        # 1) Metadata similarity: averaged across all seeds
        similarities = []
        strongest_overlap = 0
        for seed_profile in seed_profiles:
            sim = calculate_similarity(seed_profile.properties, profile.properties)
            if sim > 0:
                similarities.append(sim)
            strongest_overlap = max(strongest_overlap, _count_property_overlap(seed_profile.properties, profile.properties))

        avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0

        # 2) Embedding similarity (optional)
        embed_score = _embedding_similarity(seed_embed_ids, profile.embedding_id)

        # 3) Genre overlap gating (but softer, embedding can compensate)
        candidate_genres = profile.properties.get('genre', set())
        genre_jaccard = 0.0
        min_genre_jaccard = 0.12 if lenient_genre_filter else 0.32
        if seed_genre_union and candidate_genres:
            overlap_count = len(candidate_genres & seed_genre_union)
            union_count = len(candidate_genres | seed_genre_union)
            genre_jaccard = overlap_count / union_count if union_count else 0.0
            # Reward strong metadata matches and embeddings by relaxing the threshold
            if embed_score >= 0.75:
                min_genre_jaccard *= 0.6
            elif embed_score >= 0.6:
                min_genre_jaccard *= 0.8

            if strongest_overlap >= 3:
                min_genre_jaccard *= 0.85

            if genre_jaccard < min_genre_jaccard:
                # Allow high embedding matches to skip genre gating entirely
                if embed_score < 0.65 and strongest_overlap < 2:
                    continue
        elif seed_genre_union and not candidate_genres:
            if embed_score < 0.65 and strongest_overlap < 2:
                continue

        metadata_ok = avg_similarity >= _PROPERTY_SIM_THRESHOLD or strongest_overlap >= 2
        if not metadata_ok and embed_score < 0.6:
            continue

        # Rating bonus keeps high-signal films near the top
        rating_bonus = 0.0
        if profile.rating is not None:
            rating_norm = max(0.0, min((profile.rating - 6.0) / 4.0, 1.0))
            rating_bonus = 0.12 * rating_norm

        combined_score = ((1 - _EMBED_WEIGHT) * avg_similarity) + (_EMBED_WEIGHT * embed_score)
        combined_score += rating_bonus
        combined_score += 0.01 * strongest_overlap  # prefer movies sharing multiple facets

        # Mild penalty so identical-seeming clones do not always dominate
        if genre_jaccard > 0.85 and strongest_overlap >= 4:
            combined_score *= 0.97

        if combined_score <= 0:
            continue

        seen_titles.add(label.lower())
        rating_for_sort = profile.rating if profile.rating is not None else 0.0
        recommendations.append((label, combined_score, rating_for_sort, str(candidate_uri)))

    # 5. Sort by similarity and return top K
    recommendations.sort(key=lambda x: (x[1], x[2]), reverse=True)
    LAST_RUN['recommendations'] = {label: uri for label, _s, _r, uri in recommendations[: max(top_k, 50)]}
    trimmed = [(label, score) for label, score, _r, _u in recommendations]
    return trimmed[:top_k]


def recommend_by_theme(graph, query_text: str, top_k: int = 5) -> List[Tuple[str, float]]:
    """
    Recommend movies based on themes/keywords when no seed titles are provided.
    Examples: "classic Disney magic", "superhero movies", "romantic comedies"

    Returns list of (movie_label, score) tuples.
    """
    # Extract potential production companies and genres from query
    LAST_RUN['seeds'] = []
    LAST_RUN['seed_names'] = []
    LAST_RUN['recommendations'] = {}
    query_lower = query_text.lower()

    # Production company mappings
    company_keywords = {
        'disney': ['Q7414', 'Q191224'],  # Walt Disney Pictures, Walt Disney Animation Studios
        'pixar': ['Q127552'],  # Pixar
        'marvel': ['Q367466'],  # Marvel Studios
        'dc': ['Q2924461'],  # DC Films
        'paramount': ['Q159846'],  # Paramount Pictures
        'warner': ['Q126399'],  # Warner Bros.
        'warner bros': ['Q126399'],  # Warner Bros.
        'universal': ['Q168383'],  # Universal Pictures
        'sony': ['Q822314'],  # Sony Pictures
        'fox': ['Q434841'],  # 20th Century Fox
        '20th century': ['Q434841'],  # 20th Century Fox
        'dreamworks': ['Q192557'],  # DreamWorks Pictures
        'mgm': ['Q179200'],  # Metro-Goldwyn-Mayer
        'lionsgate': ['Q848599'],  # Lionsgate Films
        'columbia': ['Q186941'],  # Columbia Pictures
        'new line': ['Q79202'],  # New Line Cinema
        'a24': ['Q23781464'],  # A24
        'miramax': ['Q531099'],  # Miramax
    }

    # Genre / theme keywords (maps keyword -> list of canonical genre labels)
    genre_keywords = {
        # Core genres
        'action': ['action film'],
        'adventure': ['adventure film'],
        'comedy': ['comedy film'],
        'drama': ['drama film'],
        'horror': ['horror film'],
        'thriller': ['thriller film'],
        'romance': ['romance film'],
        'romantic': ['romantic comedy', 'romance film'],
        'sci-fi': ['science fiction film'],
        'science fiction': ['science fiction film'],
        'fantasy': ['fantasy film'],
        'animated': ['animated film', 'animation film'],
        'animation': ['animated film', 'animation film'],
        'family': ['family film'],
        'kids': ['family film'],

        # Seasonal / holiday themes
        'christmas': ['christmas film', 'holiday film'],
        'xmas': ['christmas film', 'holiday film'],
        'noel': ['christmas film'],
        'holiday': ['christmas film', 'holiday film'],
        'winter': ['christmas film'],
        'halloween': ['horror film', 'slasher film'],

        # Horror subgenres
        'slasher': ['slasher film'],
        'ghost': ['ghost film'],
        'haunted': ['ghost film'],
        'witch': ['witchcraft film'],
        'zombie': ['zombie film'],
        'vampire': ['vampire film'],
        'werewolf': ['werewolf film'],
        'monster': ['monster film'],
        'psychological': ['psychological horror'],
        'occult': ['occult film'],

        # Crime / suspense
        'crime': ['crime film'],
        'detective': ['detective film', 'mystery film'],
        'mystery': ['mystery film'],
        'noir': ['film noir', 'neo-noir'],
        'heist': ['heist film'],
        'bank robbery': ['heist film'],
        'spy': ['spy film'],
        'espionage': ['spy film'],
        'secret agent': ['spy film'],
        'courtroom': ['legal drama'],
        'legal': ['legal drama'],
        'political': ['political thriller'],

        # Warfare / historical
        'war': ['war film'],
        'world war': ['war film'],
        'military': ['war film'],
        'historical': ['historical film'],
        'biopic': ['biographical film'],
        'biographical': ['biographical film'],
        'true story': ['biographical film'],
        'documentary': ['documentary film'],

        # Sci-fi subgenres
        'space': ['space opera'],
        'space opera': ['space opera'],
        'dystopia': ['dystopian film'],
        'dystopian': ['dystopian film'],
        'post-apocalyptic': ['post-apocalyptic film'],
        'apocalypse': ['post-apocalyptic film'],
        'cyberpunk': ['cyberpunk film'],
        'time travel': ['time travel film'],

        # Western / eastern
        'western': ['western'],
        'samurai': ['jidaigeki'],
        'martial arts': ['martial arts film'],
        'kung fu': ['martial arts film'],

        # Sports
        'sports': ['sports film'],
        'baseball': ['sports film'],
        'basketball': ['sports film'],
        'football': ['sports film'],
        'soccer': ['sports film'],
        'boxing': ['sports film'],
        'racing': ['auto racing film'],

        # Youth / coming-of-age
        'teen': ['teen film'],
        'coming of age': ['coming-of-age story'],
        'coming-of-age': ['coming-of-age story'],
        'high school': ['teen film'],
        'college': ['teen film'],

        # Other identifiable vibes
        'superhero': ['superhero film'],
        'comic book': ['superhero film'],
        'musical': ['musical film'],
        'musician': ['musical film'],
        'romcom': ['romantic comedy'],
        'holiday romance': ['christmas film', 'romantic comedy'],
        'gothic': ['gothic horror'],
        'steampunk': ['steampunk'],
        'survival': ['survival film'],
        'road trip': ['road movie'],
        'buddy': ['buddy comedy'],
    }

    # Find matching companies and genres
    target_companies = []
    target_genres = []

    for keyword, qids in company_keywords.items():
        if keyword in query_lower:
            target_companies.extend(qids)

    for keyword, genres in genre_keywords.items():
        if keyword in query_lower:
            for genre in genres:
                if genre not in target_genres:
                    target_genres.append(genre)

    if not target_companies and not target_genres:
        return []

    print(f"[recommender] Theme-based search - Companies: {target_companies}, Genres: {target_genres}")

    # Find all films in graph
    p31_uri = rdflib.URIRef('http://www.wikidata.org/prop/direct/P31')
    film_uri = rdflib.URIRef('http://www.wikidata.org/entity/Q11424')
    production_company_prop = rdflib.URIRef('http://www.wikidata.org/prop/direct/P272')
    genre_prop = rdflib.URIRef('http://www.wikidata.org/prop/direct/P136')

    candidates = []

    for movie_uri in graph.subjects(p31_uri, film_uri):
        score = 0.0

        # Check production company match
        if target_companies:
            for company_uri in graph.objects(movie_uri, production_company_prop):
                company_qid = _qid_from_uri(str(company_uri))
                if company_qid in target_companies:
                    score += 2.0  # High weight for company match

        # Check genre match
        if target_genres:
            for genre_uri in graph.objects(movie_uri, genre_prop):
                # Get genre label
                for label_obj in graph.objects(genre_uri, RDFS.label):
                    genre_label = str(label_obj).lower()
                    for target_genre in target_genres:
                        if target_genre in genre_label or genre_label in target_genre:
                            score += 1.0
                            break

        # Only include if there's a match
        if score > 0:
            # Get movie label
            label = None
            for obj in graph.objects(movie_uri, RDFS.label):
                label = str(obj)
                break

            if label:
                candidates.append((label, score, movie_uri))

    # Sort by score; among equal scores, the better-documented (better-known) film first
    def _depth(uri):
        return sum(1 for _ in graph.predicate_objects(uri))

    candidates.sort(key=lambda x: (x[1], _depth(x[2])), reverse=True)
    print(f"[recommender] Found {len(candidates)} theme-based candidates")
    LAST_RUN['seeds'] = []
    LAST_RUN['recommendations'] = {label: str(uri) for label, _s, uri in candidates[: max(top_k, 50)]}
    return [(label, score) for label, score, _u in candidates[:top_k]]


def _qid_from_uri(uri_str: str) -> str:
    """Extract QID from Wikidata URI."""
    if isinstance(uri_str, str) and uri_str.startswith('http://www.wikidata.org/entity/'):
        return uri_str.split('/')[-1]
    return None
