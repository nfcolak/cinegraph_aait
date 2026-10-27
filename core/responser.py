# responser.py
# Core responder: parse entity and relation from a question,
# query the local RDF graph, and format a factual answer.

import re
import os
import time
import rdflib
import numpy as np
from rdflib.namespace import RDFS

from core.data import build_label_maps, WD, load_ratings, load_image_map
from core.entity import extract_title, resolve_entity
from core.relation import parse_relation, resolve_property_uri_from_local
from core.query import ONE_QID_ONE_RELATION, ONE_LABEL_ONE_RELATION
from core.intent import parse_intent, USE_THRESHOLD
from core.linker import get_linker, normalize, STOP
from core.recommender import (
    is_recommendation_question,
    extract_movie_titles,
    recommend_movies,
    recommend_by_theme,
    extract_constraints,
    recommend_movies_with_constraints,
    configure_embedding_similarity,
    detect_actor_based_recommendation,
    detect_director_based_recommendation,
    detect_composer_based_recommendation,
    detect_screenwriter_based_recommendation,
    detect_production_company_based_recommendation,
    detect_language_based_recommendation,
    resolve_movie_uri,
    LAST_RUN as REC_LAST_RUN,
)

# --- Global Natural Language Templates for Formatting Answers ---
NL_TEMPLATES = {
    "director": {
        "forward": "The movie was directed by {answers}.",
        "inverse": "Movies directed by {title_phrase} include {answers}.",
    },
    "screenwriter": {
        "forward": "The screenplay was written by {answers}.",
        "inverse": "Movies written by {title_phrase} include {answers}.",
    },
    "composer": {
        "forward": "The music was composed by {answers}.",
        "inverse": "Movies scored by {title_phrase} include {answers}.",
    },
    "genre": {
        "forward": "The {genre_word} {is_are} {answers}.",
    },
    "nominated for": {
        "forward": "{title_phrase} was nominated for {answers}.",
    },
    "award received": {
        "forward": "{title_phrase} won {answers}.",
    },
    "country of origin": {
        "forward": "The movie is from {answers}.",
    },
    "publication date": {
        "forward": "The movie was released on {answers}.",
    },
}

# Sentences the intent path uses for relations without a NL_TEMPLATES entry
INTENT_FORWARD = {
    "cast member": "The cast of {title_phrase} includes {answers}.",
    "producer": "{title_phrase} was produced by {answers}.",
    "production company": "{title_phrase} was produced by {answers}.",
    "distributed by": "{title_phrase} was distributed by {answers}.",
    "cinematographer": "The cinematographer of {title_phrase} was {answers}.",
    "original language": "The original language of {title_phrase} is {answers}.",
}
INTENT_INVERSE = {
    "cast member": "Movies with {who} include {answers}.",
    "producer": "Movies produced by {who} include {answers}.",
    "production company": "Movies produced by {who} include {answers}.",
    "distributed by": "Movies distributed by {who} include {answers}.",
    "cinematographer": "Movies shot by {who} include {answers}.",
}

# Genre word (Intent.genre) -> QID, same table as the old inverse path
GENRE_QIDS = {
    'biographical': 'Q645928', 'biography': 'Q645928', 'action': 'Q188473',
    'comedy': 'Q157443', 'drama': 'Q130232', 'horror': 'Q200092', 'thriller': 'Q182015',
    'romance': 'Q861243', 'romantic': 'Q861243', 'sci-fi': 'Q471839', 'fantasy': 'Q157394',
    'documentary': 'Q93204', 'animated': 'Q202866', 'musical': 'Q2743', 'western': 'Q172980',
    'crime': 'Q959790', 'mystery': 'Q1200678',
}

# --- Intent path settings ---
FACT_KINDS = {"film", "character", "series"}      # subjects of a fact question
FILMS_OF_KINDS = {"person", "company"}            # subjects of a films_of question
VIA_FILMS_KINDS = {"character", "series"}         # answered through their linked films
MIN_SPAN_COVERAGE = 0.6   # a span match must cover this share of the mention's tokens
MAX_VIA_VALUES = 6        # values listed for a non-film subject
MAX_FILMS_LISTED = 10     # films named in a films_of answer
MAX_ALTERNATIVES = 5
LINK_LIMIT = 10

# --- Multimedia patterns (from respo1) ---

_MULTIMEDIA_PATTERNS = [
    # 1. Explicit Image Requests
    # "Show me a picture...", "I want to see an image..."
    r'\b(?:show|give|display|see|view|want|find)\s+(?:me\s+)?(?:a\s+|an\s+|the\s+)?(?:picture|image|photo|pic|poster|shot|frame|still)s?\b',
    # "Image of...", "Poster for..." (Start of sentence or distinct phrase)
    r'^(?:picture|image|photo|pic|poster|shot|frame|still)s?\s+(?:of|from|for|with|featuring)\b',
    r'\bimage\s+of\b',

    # 2. "Look Like" Queries
    # "What does X look like", "How does X look", "Can you show me what X looks like"
    r'\b(?:what|how)\s+(?:does|do|did|can|could|would)?\s*(?:.+)\s+looks?\s*(?:like)?\b',
    r'\blooks?\s+like\b',

    # 3. Direct "Show me [Entity]"
    # Catch "Show me [Person]" but try to avoid "Show me movies"
    # We rely on the Entity Resolution later to determine if it's a person or movie.
    r'\b(?:show|display|see|view)\s+(?:me\s+)?([A-Z][a-zA-Z0-9\-\.]+(?:\s+[A-Z][a-zA-Z0-9\-\.]+)*)\s*[\.\?!]?$',
    r'\blet\s+me\s+see\s+([A-Z][a-zA-Z0-9\-\.]+(?:\s+[A-Z][a-zA-Z0-9\-\.]+)*)\s*[\.\?!]?$',

    # 4. Specific Backdrops/Scenes - VERY RESTRICTIVE
    # Only explicit "scene from" patterns
    r'\bscene\s+from\b',
    r'\bin\s+a\s+scene\b',
]

# ---------- Config ----------

# If True: URI sonuçlarında label yoksa o sonucu hiçbir şekilde döndürme.
# If False: URI sonuçlarında label yoksa QID döndür (en azından bir bilgi ver).
STRICT_LABELS = False


# ---------- Helpers ----------

_QID_RE = re.compile(r"^Q\d+$")


def _qid_from_uri(uri):
    """Extract the Wikidata-style QID from a WD URI/str, else return None."""
    s = str(uri)
    pref = str(WD)  # 'http://www.wikidata.org/entity/'
    return s[len(pref):] if s.startswith(pref) else None


# Global cache for QID to label lookups
_qid_label_cache = {}


def qid_to_label(graph, qid: str, pref_lang: str = "en"):
    """
    Return a human label for QID with caching.
    Preference order: pref_lang -> any language -> None.
    """
    if not qid or not _QID_RE.match(qid):
        return None

    # Check cache first
    cache_key = (qid, pref_lang)
    if cache_key in _qid_label_cache:
        return _qid_label_cache[cache_key]

    # 1) Preferred language (e.g., English)
    try:
        rows = graph.query(f"""
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX wd:   <http://www.wikidata.org/entity/>
            SELECT ?l WHERE {{
              wd:{qid} rdfs:label ?l .
              FILTER (lang(?l)='{pref_lang}')
            }} LIMIT 1
        """)
        for (l,) in rows:
            ls = str(l).strip()
            if ls:
                _qid_label_cache[cache_key] = ls
                return ls
    except Exception:
        pass

    # 2) Any language
    try:
        rows = graph.query(f"""
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX wd:   <http://www.wikidata.org/entity/>
            SELECT ?l WHERE {{
              wd:{qid} rdfs:label ?l .
            }} LIMIT 1
        """)
        for (l,) in rows:
            ls = str(l).strip()
            if ls:
                _qid_label_cache[cache_key] = ls
                return ls
    except Exception:
        pass

    _qid_label_cache[cache_key] = None
    return None


def _label_from_uri_strict(graph, uri):
    """
    Label resolver with optional QID fallback.
    """
    if not isinstance(uri, rdflib.term.URIRef):
        return None

    # 1) preferredLabel (English)
    try:
        pl = graph.preferredLabel(uri, lang="en")
        if pl and pl[0][1]:
            val = str(pl[0][1]).strip()
            if val:
                return val
    except Exception:
        pass

    # 2) SPARQL English label
    try:
        rows = list(graph.query(f"""
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT ?l WHERE {{ <{uri}> rdfs:label ?l .
                              FILTER (lang(?l)='en') }}
            LIMIT 1
        """))
        if rows:
            lab = str(rows[0][0]).strip()
            if lab:
                return lab
    except Exception:
        pass

    # 3) Any-language label (first available)
    try:
        lab_any = graph.value(uri, RDFS.label)
        if lab_any:
            lab_s = str(lab_any).strip()
            if lab_s:
                return lab_s
    except Exception:
        pass

    # 4) Fallback to QID if not in strict mode
    if not STRICT_LABELS:
        qid = _qid_from_uri(uri)
        if qid:
            return qid  # Return QID (e.g., "Q12345") as last resort

    # 5) Strict mode: no fallback
    return None


def _escape_literal_for_query(s: str) -> str:
    """Escape backslashes and double quotes for SPARQL string literal."""
    return s.replace("\\", r"\\").replace('"', r"\"")


def _prioritize_film_entities(graph, candidates):
    """
    Reorder entity candidates to prefer films (P31=Q11424).
    """
    if not candidates:
        return candidates

    p31 = rdflib.URIRef("http://www.wikidata.org/prop/direct/P31")
    film = rdflib.URIRef("http://www.wikidata.org/entity/Q11424")
    ratings_map = load_ratings(use_cache=True)
    date_prop = rdflib.URIRef("http://www.wikidata.org/prop/direct/P577")

    def sort_key(uri):
        is_film = (uri, p31, film) in graph
        rating = ratings_map.get(str(uri), 0.0)
        # Films get priority, then by rating
        priority_score = rating if is_film else -10.0
        
        # Determine if it's a person (Q5) for secondary sorting if needed?
        # For now, just prioritizing films is enough for Title collisions.
        
        return (is_film, priority_score)

    candidates.sort(key=sort_key, reverse=True)
    return candidates

def _is_person_entity(graph, uri):
    """Check if entity is a human (Q5)."""
    p31 = rdflib.URIRef("http://www.wikidata.org/prop/direct/P31")
    human = rdflib.URIRef("http://www.wikidata.org/entity/Q5")
    return (uri, p31, human) in graph

def _is_film_entity_check(graph, uri):
    """Check if entity is a film (Q11424)."""
    p31 = rdflib.URIRef("http://www.wikidata.org/prop/direct/P31")
    film = rdflib.URIRef("http://www.wikidata.org/entity/Q11424")
    return (uri, p31, film) in graph


# --- Multimedia helpers (from respo1) ---

_IMAGE_MAP = {}

# Structured details of the last image lookup (read by the web API; requests are serialized there)
_LAST_IMAGE_META = {}


def is_multimedia_query(text: str) -> bool:
    """Detect if the question is asking for a picture/image."""
    query_lower = text.lower().strip()
    
    # Check if user is asking for "movies" generally (Factual) vs "picture of movie" (Multimedia)
    # If the query contains "show me movies", "list movies", etc., it's likely factual/recommendation
    # unless it explicitly asks for "poster" or "picture".
    if re.search(r'\b(?:show|list|recommend)\s+(?:me\s+)?(?:some\s+)?(?:movies?|films?)\b', query_lower):
         if not re.search(r'\b(?:poster|picture|image|photo)\b', query_lower):
             return False

    for pattern in _MULTIMEDIA_PATTERNS:
        if re.search(pattern, query_lower):
            return True
    return False


def _qid_to_imdb_id(graph, entity_uri: str):
    """
    Looks up the IMDB ID (nm.../tt...) for a given entity URI (QID) in the graph.
    IMDB ID property: wdt:P345
    """
    rows = list(graph.query(f"""
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        SELECT ?imdb WHERE {{ <{entity_uri}> wdt:P345 ?imdb . }}
        LIMIT 1
    """))
    if rows:
        return str(rows[0][0]).strip()
    return None


def _resolve_image_url(message, graph, lbl_to_ent):
    """
    Robustly extracts entity name, resolves URI, and returns image path.
    Prioritizes person images for person queries, movie posters for movie queries.
    Handles 'backdrop' (scene) queries for both movies and actors.
    """
    global _IMAGE_MAP

    _LAST_IMAGE_META.clear()

    if not _IMAGE_MAP:
        from core.data import load_image_map
        _IMAGE_MAP.update(load_image_map(use_cache=True))

    # --- 1. Detection Strategy ---

    # A. Detect BACKDROP intent - VERY RESTRICTIVE
    # Only match explicit "scene from" or "in a scene" patterns
    backdrop_indicators = [
        r'\bscene\s+from\b',  # "scene from [Movie]"
        r'\bin\s+a\s+scene\b',  # "[Actor] in a scene"
        r'\bshow\s+(?:me\s+)?(?:a\s+)?scene\b',  # "show me a scene"
    ]
    is_backdrop_query = any(re.search(pattern, message, re.IGNORECASE) for pattern in backdrop_indicators)

    # B. Detect MOVIE/POSTER intent
    movie_indicators = [
        r'\b(?:poster|movie|film)\b',
        r'\bshow\s+(?:me\s+)?(?:the\s+)?(?:poster|movie)',
        r'\bpicture\s+of\s+(?:the\s+)?(?:movie|film)\b', 
    ]
    is_movie_query = any(re.search(pattern, message, re.IGNORECASE) for pattern in movie_indicators)

    # C. Detect PERSON intent (Fallback)
    person_indicators = [
        r'\b(?:actor|actress|person|guy|girl|star|celebrity)\b',
        r'\blook[s]?\s*like\b',
        r'\bpicture\s+of\s+(?!the\s+movie|the\s+film)', 
        r'\bphoto\s+of\s+(?!the\s+movie|the\s+film)',
        r'\bimage\s+of\s+(?!the\s+movie|the\s+film)',
        r'\bshow\s+me\s+[A-Z]', # Heuristic: Show me [Name]
    ]
    is_person_query = any(re.search(pattern, message, re.IGNORECASE) for pattern in person_indicators)
    
    # Determine Target Map
    target_map_type = 'profile' # default
    if is_backdrop_query:
        target_map_type = 'backdrop'
    elif is_movie_query:
        target_map_type = 'poster'
    
    print(f"[multimedia] Detected Intent: {target_map_type.upper()}")

    # --- 2. Clean Message & Extract Entity ---
    clean_msg = message
    
    # Remove possessive suffixes
    clean_msg = re.sub(r"['’]s\s+", " ", clean_msg, flags=re.IGNORECASE)
    
    # Noise Stripping
    noise_patterns = [
        r'\b(?:do\s+you\s+know|i\s+want\s+to\s+know|let\s+me\s+know|tell\s+me)\b',
        r'\b(?:can|could|would|will|may)\s+(?:you|i|we)\s+(?:please\s+)?(?:even\s+)?(?:just\s+)?',
        r'\b(?:i|we)\s+(?:want|would\s+like)\s+to\s+',
        r'\b(?:hey|hi|hello|umm|uh|please|kindly|maybe|just)\b',
        r'\b(?:show|give|display|let|get|find|see|view|watch|check)\b\s+(?:me|us)?',
        r'\b(?:what|how)\s+(?:does|do|did|is|exactly)\b',
        r'\b(?:what|how)\s+', 
        r'\b(?:the\s+)?(?:official\s+)?(?:movie|film)?\s*(?:picture|image|photo|pic|poster|shot|still|frame|scene|backdrop)s?\s+(?:of|for|from|about|with|featuring)\b',
        r'\b(?:picture|image|photo|pic|poster|shot|scene|backdrop)s?\b', 
        r'\blooks?\s+like\b\??',
        r'\blooks?\b\??',
        r'\bin\s+a\s+scene\b', 
        r'^\s*(?:the|an|a|i)\s+',
    ]
    
    for pattern in noise_patterns:
        clean_msg = re.sub(pattern, '', clean_msg, flags=re.IGNORECASE)
    
    # Remove "movie" or "film" prefix if present and not needed (e.g. "movie Titanic")
    # But keep it if it's "movie poster" (handled above)
    clean_msg = re.sub(r'^\s*(?:movie|film)\s+', '', clean_msg, flags=re.IGNORECASE)
    
    # Aggressive Punctuation Strip
    entity_name = clean_msg.strip().strip(".,!?;:'\"-")
    
    # Manual typo fixes
    if entity_name.lower() == "forest gump": 
        entity_name = "Forrest Gump"
    if "hatheway" in entity_name.lower(): 
        entity_name = "Anne Hathaway"

    # Handle "Actor in Movie" split for Backdrops
    candidates = [entity_name]
    actor_movie_split = False
    if target_map_type == 'backdrop' and (' in ' in entity_name or ' from ' in entity_name):
         # Split and try to resolve parts.
         # e.g. "Brad Pitt in Fight Club" -> ["Brad Pitt", "Fight Club"]
         parts = re.split(r'\s+(?:in|from)\s+', entity_name)
         candidates = parts + [entity_name]
         actor_movie_split = len(parts) >= 2

    print(f"[multimedia] Extraction Candidates: {candidates}")

    # --- 3. Resolve Entity and Refine Intent ---
    resolved_uri = None
    resolved_movie_uri = None  # For actor+movie backdrop queries
    final_map_type = target_map_type

    # Try to resolve both actor and movie if split detected
    if target_map_type == 'backdrop' and actor_movie_split and len(candidates) >= 2:
        # First candidate is likely the actor, second is the movie
        actor_candidate = candidates[0].strip()
        movie_candidate = candidates[1].strip()

        actor_uris = resolve_entity(graph, lbl_to_ent, actor_candidate)
        movie_uris = resolve_entity(graph, lbl_to_ent, movie_candidate)

        if actor_uris and movie_uris:
            actor_uri = actor_uris[0]
            movie_uri = movie_uris[0]

            if _is_person_entity(graph, actor_uri) and _is_film_entity_check(graph, movie_uri):
                print(f"[multimedia] Resolved Actor+Movie: {actor_candidate} + {movie_candidate}")
                resolved_uri = actor_uri
                resolved_movie_uri = movie_uri
                final_map_type = 'backdrop_cast'  # Special handling below

    # Fallback: Standard resolution if actor+movie not found
    if not resolved_uri:
        for cand in candidates:
            if not cand or len(cand) < 2: continue

            # Resolve candidate
            uris = resolve_entity(graph, lbl_to_ent, cand)
            if not uris: continue

            uri = uris[0] # Take best match

            # Check type
            is_person = _is_person_entity(graph, uri)
            is_film = _is_film_entity_check(graph, uri)

            # If we are looking for a BACKDROP:
            if target_map_type == 'backdrop':
                if is_person:
                    # Found an actor (e.g., "Brad Pitt") -> Use backdrop_cast
                    print(f"[multimedia] Resolved '{cand}' as Person. Switching to backdrop_cast.")
                    resolved_uri = uri
                    final_map_type = 'backdrop_cast'
                    break # Prioritize Actor for "Actor in Movie" queries
                elif is_film:
                    # Found a film -> Use backdrop
                    print(f"[multimedia] Resolved '{cand}' as Movie.")
                    resolved_uri = uri
                    final_map_type = 'backdrop'
                    break

            # If we are looking for PROFILE:
            elif target_map_type == 'profile':
                if is_person:
                    resolved_uri = uri
                    break

            # If we are looking for POSTER:
            elif target_map_type == 'poster':
                if is_film:
                    resolved_uri = uri
                    break

            # Generic fallback if type mismatch but high confidence resolution?
            # e.g. User asked for "Poster of Brad Pitt" (Technically profile, or poster of a movie he's in?)
            # Let's stick to strict types for now to avoid bad matches, but allow fallback if nothing found.
            if not resolved_uri:
                resolved_uri = uri # tentative match

    if not resolved_uri and candidates:
         # Last ditch: Try first candidate with loose typing
         uris = resolve_entity(graph, lbl_to_ent, candidates[0])
         if uris: resolved_uri = uris[0]

    if not resolved_uri:
        return None, f"Could not identify the person or movie '{entity_name}'."

    nice_name = qid_to_label(graph, _qid_from_uri(resolved_uri)) or entity_name
    _LAST_IMAGE_META.update(
        entity_uri=str(resolved_uri),
        entity_label=nice_name,
        movie_uri=str(resolved_movie_uri) if resolved_movie_uri else None,
        kind=final_map_type,
    )

    # --- 4. Get IMDB ID and Lookup Image ---
    imdb_id = _qid_to_imdb_id(graph, resolved_uri)
    movie_imdb_id = None
    if resolved_movie_uri:
        movie_imdb_id = _qid_to_imdb_id(graph, resolved_movie_uri)

    if not imdb_id:
        return None, f"Found {nice_name}, but no IMDB ID is linked."

    print(f"[multimedia] Looking up IMDB ID: {imdb_id} in map: {final_map_type}")
    if movie_imdb_id:
        print(f"[multimedia] Movie filter IMDB ID: {movie_imdb_id}")

    # Special handling for Actor+Movie backdrop queries
    if final_map_type == 'backdrop_cast' and movie_imdb_id:
        combo_lookup = _IMAGE_MAP.get('backdrop_actor_movie') or {}
        movie_lookup = combo_lookup.get(imdb_id, {})
        combo_image = movie_lookup.get(movie_imdb_id) if movie_lookup else None

        if combo_image:
            print("[multimedia] Found cached actor+movie backdrop match.")
            _LAST_IMAGE_META['kind'] = 'backdrop_cast'
            folder_id, filename_with_ext = os.path.split(combo_image)
            filename_hash, _ = os.path.splitext(filename_with_ext)
            return f"image:{folder_id}/{filename_hash}", None

    # Standard Lookup (fallback or non-actor+movie queries)
    specific_map = _IMAGE_MAP.get(final_map_type, {})
    image_path = specific_map.get(imdb_id)

    # Fallback Logic
    if not image_path:
        print(f"[multimedia] Image not found in {final_map_type}. Trying fallbacks.")
        # Try all maps
        for fallback in ['backdrop_cast', 'backdrop', 'profile', 'poster']:
             if fallback == final_map_type: continue
             image_path = _IMAGE_MAP.get(fallback, {}).get(imdb_id)
             if image_path:
                 print(f"[multimedia] Fallback: Found image in {fallback} map.")
                 _LAST_IMAGE_META['kind'] = fallback
                 break

    if image_path:
        folder_id, filename_with_ext = os.path.split(image_path)
        filename_hash, _ = os.path.splitext(filename_with_ext)
        return f"image:{folder_id}/{filename_hash}", None
    else:
        return None, f"Found {nice_name} ({imdb_id}), but no image available."


# ---------- Responser ----------

class Responser:
    """Stateless responder that works only with the local graph."""
    def __init__(self, entity_embeds=None, relation_embeds=None,
                 ent_uri_to_id=None, rel_uri_to_id=None, id_to_ent_uri=None):
        # Optional embeddings (for embedding-based fallback/answers)
        self.entity_embeds = entity_embeds
        self.relation_embeds = relation_embeds
        self.ent_uri_to_id = ent_uri_to_id
        self.rel_uri_to_id = rel_uri_to_id
        self.id_to_ent_uri = id_to_ent_uri

        # Share embedding resources with the recommender for blended similarity scoring
        if self.entity_embeds is not None and self.ent_uri_to_id is not None:
            configure_embedding_similarity(self.entity_embeds, self.ent_uri_to_id)
        else:
            configure_embedding_similarity(None, None)

        # Cache for label lookups to avoid repeated queries
        self._label_cache = {}

        # Filled by generate_response(); see there for the keys
        self.last_meta: dict = {'answer_uris': [], 'recommendations': [], 'seeds': []}

    # ----- factual -----

    def _format_natural_answer(
        self,
        rel_label: str,
        answers: list,
        title: str = None,
        inverse_query: bool = False,
    ) -> str:
        """
        Format factual answers in natural human language.
        """
        if not answers:
            return None

        templates = NL_TEMPLATES

        if rel_label == "genre":
            genre_word = "genre is" if len(answers) == 1 else "genres are"
            answer_text = " and ".join(answers)
            return f"The {genre_word} {answer_text}."

        template_info = templates.get(rel_label)
        if template_info:
            template_key = "inverse" if inverse_query else "forward"
            template = template_info.get(template_key) or template_info.get("forward")
            if template:
                if inverse_query:
                    title_phrase = title or "this person"
                else:
                    title_phrase = f'"{title}"' if title else "The movie"
                answer_text = " and ".join(answers)
                return template.format(answers=answer_text, title_phrase=title_phrase)

        answer_text = " and ".join(answers)
        return answer_text

    def _generate_language_based_response(self, message, graph, language_qid, lbl_to_ent):
        """
        Generate response for language-based queries like
        "Which action movies have original language Japanese?"
        """
        genre_filter = ""
        genre_keywords = {
            'biographical': 'Q645928',
            'biography': 'Q645928',
            'action': 'Q188473',
            'comedy': 'Q157443',
            'drama': 'Q130232',
            'horror': 'Q200092',
            'thriller': 'Q182015',
            'romance': 'Q861243',
            'romantic': 'Q861243',
            'sci-fi': 'Q471839',
            'fantasy': 'Q157394',
            'documentary': 'Q93204',
            'animated': 'Q202866',
            'musical': 'Q2743',
            'western': 'Q172980',
            'crime': 'Q959790',
            'mystery': 'Q1200678',
        }

        for genre_keyword, genre_qid in genre_keywords.items():
            if genre_keyword in message.lower():
                genre_filter = f"?movie wdt:P136 wd:{genre_qid} ."
                print(f"[responser] Adding genre filter: {genre_keyword} (QID: {genre_qid})")
                break

        sparql = f"""
            PREFIX wd: <http://www.wikidata.org/entity/>
            PREFIX wdt: <http://www.wikidata.org/prop/direct/>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT ?movie ?movieLabel WHERE {{
                ?movie wdt:P31 wd:Q11424 .
                ?movie wdt:P364 wd:{language_qid} .
                {genre_filter}
                OPTIONAL {{ ?movie rdfs:label ?movieLabel FILTER (lang(?movieLabel) = "en") }}
            }}
            LIMIT 10
        """

        try:
            rows = list(graph.query(sparql))
        except Exception as e:
            print(f"[responser] SPARQL error: {e}")
            return None, False, "Could not execute language-based query."

        answers = []
        self.last_meta['sparql'] = sparql
        for row in rows:
            movie_uri = row[0]
            if isinstance(movie_uri, rdflib.term.URIRef):
                self.last_meta['answer_uris'].append(str(movie_uri))
            label_term = row[1] if len(row) > 1 else None

            if label_term:
                answers.append(str(label_term).strip())
            elif isinstance(movie_uri, rdflib.term.URIRef):
                lbl = _label_from_uri_strict(graph, movie_uri)
                if lbl:
                    answers.append(lbl)

        if not answers:
            return None, False, "Could not find movies with the specified language."

        seen = set()
        uniq = []
        for a in answers:
            if a not in seen:
                seen.add(a)
                uniq.append(a)

        if len(uniq) == 1:
            response = f"Based on the language filter, I found: {uniq[0]}."
        elif len(uniq) <= 5:
            response = f"Based on the language filter, I found: {', '.join(uniq[:-1])}, and {uniq[-1]}."
        else:
            response = f"Based on the language filter, I found {len(uniq)} movies including: {', '.join(uniq[:5])}, and others."

        return response, True, None

    def _generate_factual_response(self, message, graph, lbl_to_ent, pred_lbl_to_uri):
        # 1) Parse relation from the question
        rel_label = parse_relation(message)
        if not rel_label:
            return None, None, "Could not generate an answer. Please rephrase your question in a simple way."

        # 2) Resolve the property URI
        prop_uri = resolve_property_uri_from_local(pred_lbl_to_uri, rel_label)
        if not prop_uri:
            return None, None, "Could not find a property for the given question. Please rephrase your question in a simple way."

        # 3) Check if this is an inverse query (e.g., "Which movies did Eva Green direct?")
        from core.entity import extract_person_name
        inverse_query = False
        person_name = extract_person_name(message)

        if person_name:
            inverse_query = True
            print(f"[responser] Inverse query detected for person: {person_name}")

            person_uris = resolve_entity(graph, lbl_to_ent, person_name)
            if not person_uris:
                return None, False, f"Could not find '{person_name}' in the knowledge graph."

            person_uri = person_uris[0]
            person_qid = _qid_from_uri(person_uri)

            # Genre filter also for inverse queries
            genre_filter = ""
            genre_keywords = {
                'biographical': 'Q645928',
                'biography': 'Q645928',
                'action': 'Q188473',
                'comedy': 'Q157443',
                'drama': 'Q130232',
                'horror': 'Q200092',
                'thriller': 'Q182015',
                'romance': 'Q861243',
                'sci-fi': 'Q471839',
                'fantasy': 'Q157394',
                'documentary': 'Q93204',
                'animated': 'Q202866',
                'musical': 'Q2743',
                'western': 'Q172980',
                'crime': 'Q959790',
                'mystery': 'Q1200678',
            }

            for genre_keyword, genre_qid in genre_keywords.items():
                if genre_keyword in message.lower():
                    genre_filter = f"?movie wdt:P136 wd:{genre_qid} ."
                    print(f"[responser] Adding genre filter: {genre_keyword} (QID: {genre_qid})")
                    break

            if person_qid:
                sparql = f"""
                    PREFIX wd: <http://www.wikidata.org/entity/>
                    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
                    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                    SELECT ?movie ?movieLabel WHERE {{
                        ?movie <{prop_uri}> wd:{person_qid} .
                        ?movie wdt:P31 wd:Q11424 .
                        {genre_filter}
                        OPTIONAL {{ ?movie rdfs:label ?movieLabel FILTER (lang(?movieLabel) = "en") }}
                    }}
                    LIMIT 10
                """
            else:
                sparql = f"""
                    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
                    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                    SELECT ?movie ?movieLabel WHERE {{
                        ?movie <{prop_uri}> <{person_uri}> .
                        ?movie wdt:P31 <http://www.wikidata.org/entity/Q11424> .
                        {genre_filter}
                        OPTIONAL {{ ?movie rdfs:label ?movieLabel FILTER (lang(?movieLabel) = "en") }}
                    }}
                    LIMIT 10
                """

            entity_found = True
            title = person_name
            self.last_meta['entity_uri'] = str(person_uri)
        else:
            # Normal query: extract movie title
            title = extract_title(message) or message
            entity_uris = resolve_entity(graph, lbl_to_ent, title)
            entity_uris = _prioritize_film_entities(graph, entity_uris)

            entity_found = bool(entity_uris)
            qid = _qid_from_uri(entity_uris[0]) if entity_uris else None
            if entity_uris:
                self.last_meta['entity_uri'] = str(entity_uris[0])

            if qid:
                sparql = ONE_QID_ONE_RELATION % (qid, str(prop_uri))
            else:
                safe_title = _escape_literal_for_query(title)
                sparql = ONE_LABEL_ONE_RELATION % (safe_title, str(prop_uri))

        self.last_meta['relation'] = rel_label
        self.last_meta['property_uri'] = str(prop_uri)
        self.last_meta['inverse'] = inverse_query
        self.last_meta['sparql'] = sparql

        try:
            rows = list(graph.query(sparql))
        except Exception:
            rows = []

        answers = []
        for row in rows:
            obj_term = row[0]
            if isinstance(obj_term, rdflib.term.URIRef):
                self.last_meta['answer_uris'].append(str(obj_term))
            label_term = row[1] if len(row) > 1 else None

            final_answer_part = None

            if label_term is not None:
                lt = str(label_term).strip()
                if lt:
                    final_answer_part = lt

            if final_answer_part is None and obj_term is not None:
                if isinstance(obj_term, rdflib.term.URIRef):
                    lbl = _label_from_uri_strict(graph, obj_term)
                    if lbl:
                        final_answer_part = lbl
                else:
                    final_answer_part = str(obj_term).strip()

            if final_answer_part:
                if STRICT_LABELS and _QID_RE.match(final_answer_part):
                    lbl = qid_to_label(graph, final_answer_part)
                    if lbl:
                        answers.append(lbl)
                else:
                    answers.append(final_answer_part)

        if not answers:
            return None, entity_found, "Could not generate a factual answer."

        seen = set()
        uniq = []
        for a in answers:
            if a not in seen:
                seen.add(a)
                uniq.append(a)

        formatted_answer = self._format_natural_answer(rel_label, uniq, title, inverse_query=inverse_query)
        return formatted_answer, entity_found, None

    # ----- intent path -----

    @staticmethod
    def _covers(mention, cand) -> bool:
        """A span match counts only when the label holds most of the mention's words."""
        if cand.match != "span":
            return True
        toks = [t for t in normalize(mention).split() if t not in STOP]
        if not toks:
            return False
        label_toks = set(normalize(cand.label).split())
        return sum(t in label_toks for t in toks) / len(toks) >= MIN_SPAN_COVERAGE

    def _link_subject(self, linker, intent, want, message):
        """Linked candidates of a wanted kind, best first."""
        if not intent.mention:
            return []
        cands = linker.link(intent.mention, want=want, year=intent.year, question=message, limit=LINK_LIMIT)
        kept = [c for c in cands if c.kind in want and self._covers(intent.mention, c)]
        if not kept:
            # spans from the question can hide a typo match of the mention: retry on the mention alone
            cands = linker.link(intent.mention, want=want, year=intent.year, limit=LINK_LIMIT)
            kept = [c for c in cands if c.kind in want and self._covers(intent.mention, c)]
        return kept

    @staticmethod
    def _alternatives(linker, best, cands):
        """Other entities with the same name as best: same-name candidates of other kinds plus the linker's."""
        key = normalize(best.label)
        seen, out = {best.uri}, []
        for c in list(cands) + linker.alternatives(best, limit=MAX_ALTERNATIVES):
            if c.uri not in seen and normalize(c.label) == key:
                seen.add(c.uri)
                out.append(c)
        return out[:MAX_ALTERNATIVES]

    @staticmethod
    def _named_values(graph, ent_to_lbl, subject, prop_uri):
        """(uri or None, label) of every named value of subject's property."""
        out = []
        for o in graph.objects(rdflib.URIRef(str(subject)), prop_uri):
            if isinstance(o, rdflib.URIRef):
                lbl = ent_to_lbl.get(o)
                if lbl:
                    out.append((str(o), lbl))
            else:
                s = str(o).strip()
                if s:
                    out.append((None, s))
        return out

    def _fact_for_film(self, graph, ent_to_lbl, cand, prop_uri):
        """Run the ONE_QID_ONE_RELATION template on a linked film. Returns (uris, labels, sparql)."""
        sparql = ONE_QID_ONE_RELATION % (cand.qid, str(prop_uri))
        try:
            rows = list(graph.query(sparql))
        except Exception:
            rows = []
        uris, labels = [], []
        for row in rows:
            obj, lab = row[0], (row[1] if len(row) > 1 else None)
            if isinstance(obj, rdflib.URIRef):
                if lab is None or not str(lab).strip():
                    lab = ent_to_lbl.get(obj)  # labels without a language tag
                if lab is None or not str(lab).strip():
                    continue  # unnamed value: not an answer
                if str(obj) not in uris:
                    uris.append(str(obj))
                text = str(lab).strip()
            else:
                text = str(obj).strip()
            if text and text not in labels:
                labels.append(text)
        return uris, labels, sparql

    def _fact_via_films(self, graph, ent_to_lbl, films, prop_uri):
        """Values of one property over several films, most frequent first: [(uri, label, n_films)]."""
        agg = {}
        for f in films:
            seen = set()
            for uri, lbl in self._named_values(graph, ent_to_lbl, f, prop_uri):
                if lbl in seen:
                    continue
                seen.add(lbl)
                item = agg.setdefault(lbl, [uri, lbl, 0, len(agg)])
                item[2] += 1
        return [(u, l, n) for u, l, n, _ in sorted(agg.values(), key=lambda v: (-v[2], v[3]))]

    @staticmethod
    def _via_text(label, rel_label, n_films, values):
        """Answer text of design.md 1.4 for a non-film subject."""
        shown = values[:MAX_VIA_VALUES]
        if n_films == 1:
            parts = [l for _, l, _ in shown]
            head = f"{label} is not a film itself; the graph links it to 1 film. The {rel_label} of that film: "
        else:
            parts = [f"{l} ({n} film{'s' if n != 1 else ''})" for _, l, n in shown]
            head = f"{label} is not a film itself; the graph links it to {n_films} films. The {rel_label} of those films: "
        more = len(values) - len(shown)
        if more > 0:
            return head + ", ".join(parts) + f", and {more} more."
        return head + ", ".join(parts) + "."

    def _forward_text(self, rel_label, labels, title):
        if rel_label in INTENT_FORWARD:
            return INTENT_FORWARD[rel_label].format(title_phrase=f'"{title}"', answers=" and ".join(labels))
        return self._format_natural_answer(rel_label, labels, title)

    @staticmethod
    def _plural_form(intent, message) -> bool:
        """'the Toy Story movies' / 'Harry Potter films': the user means the series or character."""
        if not intent.mention or intent.quoted:
            return False
        return re.search(re.escape(intent.mention) + r"['’]?s?\s+(?:movies|films)\b", message, re.I) is not None

    def _answer_fact(self, intent, graph, linker, ent_to_lbl, prop_uri, message, kinds=FACT_KINDS):
        """One fact sub-question. Returns a result dict (answer may be None) or None when nothing linked."""
        cands = []
        if kinds is FACT_KINDS and self._plural_form(intent, message):
            for k in ({"series"}, {"character"}):
                cands = [c for c in self._link_subject(linker, intent, k, message) if c.match == "exact"]
                if cands:
                    break
        if not cands:
            cands = self._link_subject(linker, intent, kinds, message)
        if not cands:
            return None
        best = cands[0]
        res = {'relation': intent.relation, 'property_uri': str(prop_uri), 'entity_uri': best.uri,
               'cand': best, 'kind': best.kind, 'via_films': [], 'alternatives': [],
               'answer_uris': [], 'answer': None, 'sparql': None, 'inverse': False}
        if best.kind == "film":
            # films with the same name are tried in order when the best one has no value
            key = normalize(best.label)
            for c in [c for c in cands if c.kind == "film" and normalize(c.label) == key][:3]:
                uris, labels, sparql = self._fact_for_film(graph, ent_to_lbl, c, prop_uri)
                if c is best:
                    res['sparql'] = sparql
                if labels:
                    best = c
                    res.update(entity_uri=c.uri, cand=c, answer_uris=uris, sparql=sparql)
                    alts = self._alternatives(linker, c, cands)
                    res['alternatives'] = alts
                    text = self._forward_text(intent.relation, labels, c.label)
                    if alts:
                        which = f"the {c.year} film" if c.year else f"the film {c.qid}"
                        text = text.rstrip() + f" (There are {len(alts) + 1} entries called {c.label}; this is {which}.)"
                    res['answer'] = text
                    break
            return res
        # character or series: read the answer from the films linked to it
        films = linker.films_of_entity(best.uri)
        res['via_films'] = films
        res['alternatives'] = self._alternatives(linker, best, cands)
        if not films:
            return res
        values = self._fact_via_films(graph, ent_to_lbl, films, prop_uri)
        if values:
            res['answer_uris'] = [u for u, _, _ in values if u]
            res['answer'] = self._via_text(best.label, intent.relation, len(films), values)
        return res

    def _answer_films_of(self, intent, graph, linker, prop_uri, message):
        """One films_of sub-question: films whose property points at a person or company."""
        cands = self._link_subject(linker, intent, FILMS_OF_KINDS, message)
        if not cands:
            return None
        best = cands[0]
        genre_qid = GENRE_QIDS.get(intent.genre) if intent.genre else None
        genre_filter = f"?movie wdt:P136 wd:{genre_qid} ." if genre_qid else ""
        sparql = f"""
            PREFIX wd: <http://www.wikidata.org/entity/>
            PREFIX wdt: <http://www.wikidata.org/prop/direct/>
            SELECT DISTINCT ?movie WHERE {{
                ?movie <{prop_uri}> <{best.uri}> .
                ?movie wdt:P31 wd:Q11424 .
                {genre_filter}
            }}
        """
        try:
            rows = list(graph.query(sparql))
        except Exception:
            rows = []
        films = [r[0] for r in rows if isinstance(r[0], rdflib.URIRef) and linker.lbl.get(r[0])]
        # best-known films first: more triples, then title
        films.sort(key=lambda f: (-sum(1 for _ in graph.predicate_objects(f)), linker.lbl.get(f, "")))
        res = {'relation': intent.relation, 'property_uri': str(prop_uri), 'entity_uri': best.uri,
               'cand': best, 'kind': best.kind, 'via_films': [], 'alternatives': [],
               'answer_uris': [str(f) for f in films], 'answer': None, 'sparql': sparql, 'inverse': True}
        if films:
            labels = [linker.lbl[f] for f in films[:MAX_FILMS_LISTED]]
            if intent.relation in INTENT_INVERSE:
                text = INTENT_INVERSE[intent.relation].format(who=best.label, answers=" and ".join(labels))
            else:
                text = self._format_natural_answer(intent.relation, labels, best.label, inverse_query=True)
            more = len(films) - len(labels)
            if more > 0:
                text = text.rstrip(".") + f", and {more} more."
            res['answer'] = text
        return res

    def _answer_intent(self, intent, graph, linker, ent_to_lbl, pred_lbl_to_uri, message):
        """
        Answer every sub-question of an intent through the linker.
        Returns (text or None, first result or None); fills last_meta when text is returned.
        """
        memo = {}
        results = []
        for sub in [intent] + list(intent.parts):
            if not sub.relation or not sub.mention or sub.kind not in ("fact", "films_of"):
                results.append(None)
                continue
            prop_uri = resolve_property_uri_from_local(pred_lbl_to_uri, sub.relation)
            if not prop_uri:
                results.append(None)
                continue
            key = (sub.kind, sub.relation, sub.mention, sub.year, sub.genre)
            if key not in memo:
                if sub.kind == "fact":
                    memo[key] = self._answer_fact(sub, graph, linker, ent_to_lbl, prop_uri, message)
                else:
                    memo[key] = self._answer_films_of(sub, graph, linker, prop_uri, message)
                    if memo[key] is None:
                        # "Ellen Ripley's movies": a character or series, read through its films
                        memo[key] = self._answer_fact(sub, graph, linker, ent_to_lbl, prop_uri, message,
                                                      kinds=VIA_FILMS_KINDS)
            results.append(memo[key])

        first = results[0]
        answered = [r for r in results if r and r.get('answer')]
        if not answered:
            return None, first

        sentences = []
        for sub, r in zip([intent] + list(intent.parts), results):
            if r and r.get('answer'):
                sentences.append(r['answer'])
            elif sub.relation:
                about = r['cand'].label if r else (sub.mention or "it")
                sentences.append(f"I could not find the {sub.relation} of {about}.")

        lead = first if first and first.get('answer') else answered[0]
        uris = []
        for r in answered:
            uris.extend(u for u in r['answer_uris'] if u not in uris)
        self.last_meta.update(
            entity_uri=lead['entity_uri'], relation=lead['relation'], property_uri=lead['property_uri'],
            inverse=lead['inverse'], sparql=lead['sparql'], answer_uris=uris,
            intent=intent.to_dict(), subject_kind=lead['kind'], via_films=list(lead['via_films']),
            alternatives=[{'uri': c.uri, 'qid': c.qid, 'label': c.label, 'year': c.year, 'kind': c.kind}
                          for c in lead['alternatives']],
            parts=[{'relation': r['relation'] if r else s.relation,
                    'entity_uri': r['entity_uri'] if r else None,
                    'answer_uris': list(r['answer_uris']) if r and r.get('answer') else [],
                    'answer': r.get('answer') if r else None}
                   for s, r in zip([intent] + list(intent.parts), results)],
        )
        return " ".join(sentences), first

    # ----- embeddings -----

    def _get_entity_type(self, graph, entity_uri):
        """
        Query for the 'instance of' (P31) type of an entity.
        Returns a QID like 'Q5' (human) or None.
        """
        try:
            rows = list(graph.query(f"""
                PREFIX wdt: <http://www.wikidata.org/prop/direct/>
                SELECT ?type WHERE {{
                  <{entity_uri}> wdt:P31 ?type .
                }} LIMIT 1
            """))
            if rows:
                type_uri = str(rows[0][0])
                return _qid_from_uri(type_uri)
        except Exception:
            pass
        return None

    def _generate_embedding_response(self, message, graph, ent_to_lbl, lbl_to_ent, pred_lbl_to_uri,
                                     head=None, rel_label=None):
        """
        Uses a simple TransE-style approach (h + r ≈ t) to predict the tail entity (t).
        head: (uri, label) linked by the intent path; rel_label: its relation. Both optional.
        Returns (predicted_label, entity_type_qid, error)
        """
        if self.entity_embeds is None or self.relation_embeds is None:
            return None, None, "Embeddings data not loaded."

        rel_label = rel_label or parse_relation(message)
        if not rel_label:
            return None, None, "Could not parse relation for embedding query."

        prop_uri = resolve_property_uri_from_local(pred_lbl_to_uri, rel_label)
        if not prop_uri:
            return None, None, "Could not resolve property for embedding query."

        head_uri = None
        head_id = None

        if head:
            head_uri, title = str(head[0]), head[1]
            head_id = self.ent_uri_to_id.get(head_uri) if self.ent_uri_to_id else None
        else:
            title = extract_title(message) or message
            entity_uris = resolve_entity(graph, lbl_to_ent, title)
            if entity_uris:
                head_uri = str(entity_uris[0])
                head_id = self.ent_uri_to_id.get(head_uri) if self.ent_uri_to_id else None

        if head_id is None:
            return None, None, f"Entity '{title}' not found in embedding space."

        relation_uri = str(prop_uri)
        rel_id = self.rel_uri_to_id.get(relation_uri) if self.rel_uri_to_id else None
        if rel_id is None:
            return None, None, "Relation not in embedding map."

        self.last_meta['entity_uri'] = head_uri
        self.last_meta['relation'] = rel_label
        self.last_meta['property_uri'] = relation_uri

        h = self.entity_embeds[head_id]
        r = self.relation_embeds[rel_id]

        t_target = h + r
        scores = np.linalg.norm(t_target - self.entity_embeds, axis=1)
        predicted_tail_id = int(np.argmin(scores))

        predicted_tail_uri = self.id_to_ent_uri.get(predicted_tail_id) if self.id_to_ent_uri else None
        if not predicted_tail_uri:
            return None, None, "Predicted entity not found in URI map."

        predicted_tail_uri_ref = rdflib.term.URIRef(predicted_tail_uri)

        lbl = ent_to_lbl.get(predicted_tail_uri_ref) if ent_to_lbl else None
        if not lbl:
            lbl = _label_from_uri_strict(graph, predicted_tail_uri_ref)
            if lbl and _QID_RE.match(lbl):
                lbl = None  # the QID fallback is not a name

        if not lbl:
            qid = _qid_from_uri(predicted_tail_uri)
            if qid:
                lbl = qid_to_label(graph, qid)

        entity_type = self._get_entity_type(graph, predicted_tail_uri_ref)

        if not lbl:
            self.last_meta['answer_uris'] = []
            return None, entity_type, "No answer: the prediction has no name in the graph."
        self.last_meta['answer_uris'] = [predicted_tail_uri]
        return lbl, entity_type, None

    # ----- recommendation -----

    def _generate_recommendation_response(self, message, graph, precomputed_titles=None, language_filter=None):
        """
        Generate movie recommendations based on:
        1. Seed movies mentioned in the question
        2. Theme-based recommendations if no seed movies are found.
        Returns top 2 recommendations in natural language.
        """
        if not is_recommendation_question(message):
            return None, "Not a recommendation question."

        if precomputed_titles is not None:
            seed_titles = precomputed_titles
        else:
            seed_titles = extract_movie_titles(message)

        constraints = extract_constraints(message)
        if language_filter and language_filter.get('language_qid'):
            constraints = constraints or {}
            constraints['language_qid'] = language_filter['language_qid']

        recommendations = []
        top_k = 6

        if seed_titles:
            print(f"[recommender] Seed movies: {seed_titles}")
            if constraints:
                print(f"[recommender] Constraints: {constraints}")
                recommendations = recommend_movies_with_constraints(graph, seed_titles, constraints, top_k=top_k)
            else:
                recommendations = recommend_movies(graph, seed_titles, top_k=top_k)
        if not recommendations:
            if seed_titles:
                print("[recommender] Seed titles gave nothing, trying theme-based search")
            else:
                print("[recommender] No seed titles found, trying theme-based search")
            themed = recommend_by_theme(graph, message, top_k=top_k)
            if themed:
                recommendations, seed_titles = themed, []

        # Exact films behind the labels (same-named films exist), for the web cards
        seed_uris = list(REC_LAST_RUN.get('seeds') or []) if seed_titles else []
        rec_uris = REC_LAST_RUN.get('recommendations') or {}
        seed_labels = [self._label_of(graph, u) for u in seed_uris] or list(seed_titles or [])
        seed_names = list(REC_LAST_RUN.get('seed_names') or []) if seed_uris else []
        self.last_meta['seeds'] = seed_labels
        self.last_meta['seed_uris'] = seed_uris
        self.last_meta['recommendations'] = [title for title, _ in recommendations]
        self.last_meta['recommendation_uris'] = [rec_uris.get(title) for title, _ in recommendations]

        if not recommendations:
            if seed_titles and not seed_uris:
                return None, (f"I could not find {', '.join(seed_titles)} among the films in the knowledge graph. "
                              "Check the title or name another film.")
            return None, "Could not find similar movies in the knowledge graph."

        titles = [title for title, _ in recommendations]
        listed = titles[0] if len(titles) == 1 else ", ".join(titles[:-1]) + f" and {titles[-1]}"
        if seed_uris:
            response = f"If you liked {self._and_list(seed_names or seed_labels)}, try {listed}."
        else:
            response = f"Based on your preferences, I recommend {listed}."

        return response, None

    @staticmethod
    def _and_list(items):
        items = [i for i in items if i]
        if len(items) <= 1:
            return items[0] if items else ""
        return ", ".join(items[:-1]) + f" and {items[-1]}"

    @staticmethod
    def _label_of(graph, uri):
        for o in graph.objects(rdflib.URIRef(uri), RDFS.label):
            return str(o)
        return None

    # ----- public API -----

    def generate_response(self, message, graph, _WDT_ns=None, _WD_ns=None):
        start_time = time.time()
        # Structured details of this answer for the web API (route, entities, SPARQL)
        self.last_meta = {
            'route': None, 'entity_uri': None, 'relation': None, 'property_uri': None,
            'inverse': False, 'sparql': None, 'answer_uris': [], 'seeds': [],
            'recommendations': [], 'image': None, 'rewritten': None,
            'intent': None, 'subject_kind': None, 'via_films': [], 'alternatives': [], 'parts': [],
        }
        original_message = message

        # Build/retrieve lookup maps ONCE
        map_start = time.time()
        _ent_to_lbl, lbl_to_ent, pred_lbl_to_uri = build_label_maps(graph)
        map_time = time.time() - map_start
        if map_time > 0.1:
            print(f"[responser] Label maps took {map_time:.2f}s")

        # 0) Multimedia first (posters, photos, etc.)
        if is_multimedia_query(message):
            print("[responser] Detected multimedia query")
            self.last_meta['route'] = 'multimedia'
            image_result, image_error = _resolve_image_url(message, graph, lbl_to_ent)
            self.last_meta['image'] = dict(_LAST_IMAGE_META) or None
            if image_result:
                return image_result
            else:
                return image_error or "Could not find the requested image."

        # Pre-extract potential seed titles once so we can reuse
        seed_titles_hint = extract_movie_titles(message)

        # Track detected language preference separately so we can enforce it later
        language_pref = None

        # Check for language-based pseudo-recommendation
        lang_rec_info = detect_language_based_recommendation(message)
        language_qid = None
        if lang_rec_info:
            language_pref = lang_rec_info
            if seed_titles_hint:
                print(f"[responser] Skipping language-only fallback due to seed titles: {seed_titles_hint}")
                lang_rec_info = None
            else:
                print(f"[responser] Detected language-based recommendation: {lang_rec_info}")
                language = lang_rec_info.get('language')
                language_qid = lang_rec_info.get('language_qid')
                genre = lang_rec_info.get('genre')

                if genre:
                    converted_query = f"Which {genre} movies have original language {language}?"
                else:
                    converted_query = f"Which movies have original language {language}?"

                print(f"[responser] Converted to factual query: {converted_query}")
                message = converted_query
                language_pref = None  # handled via factual path

        # Person/company-based pseudo-recommendations → factual queries
        if (composer_rec_info := detect_composer_based_recommendation(message)):
            print(f"[responser] Detected composer-based recommendation: {composer_rec_info}")
            composer_name = composer_rec_info.get('composer')
            genre = composer_rec_info.get('genre')
            if genre:
                converted_query = f"Which {genre} movies did {composer_name} compose?"
            else:
                converted_query = f"Which movies did {composer_name} compose?"
            print(f"[responser] Converted to factual query: {converted_query}")
            message = converted_query

        elif (writer_rec_info := detect_screenwriter_based_recommendation(message)):
            print(f"[responser] Detected screenwriter-based recommendation: {writer_rec_info}")
            writer_name = writer_rec_info.get('screenwriter')
            genre = writer_rec_info.get('genre')
            if genre:
                converted_query = f"Which {genre} movies did {writer_name} write?"
            else:
                converted_query = f"Which movies did {writer_name} write?"
            print(f"[responser] Converted to factual query: {converted_query}")
            message = converted_query

        elif (director_rec_info := detect_director_based_recommendation(message)):
            print(f"[responser] Detected director-based recommendation: {director_rec_info}")
            director_name = director_rec_info.get('director')
            genre = director_rec_info.get('genre')
            if genre:
                converted_query = f"Which {genre} movies did {director_name} direct?"
            else:
                converted_query = f"Which movies did {director_name} direct?"
            print(f"[responser] Converted to factual query: {converted_query}")
            message = converted_query

        elif (company_rec_info := detect_production_company_based_recommendation(message)):
            print(f"[responser] Detected company-based recommendation: {company_rec_info}")
            company_name = company_rec_info.get('company')
            genre = company_rec_info.get('genre')
            if genre:
                converted_query = f"Which {genre} movies were produced by {company_name}?"
            else:
                converted_query = f"Which movies were produced by {company_name}?"
            print(f"[responser] Converted to factual query: {converted_query}")
            message = converted_query

        elif (actor_rec_info := detect_actor_based_recommendation(message)):
            print(f"[responser] Detected actor-based recommendation: {actor_rec_info}")
            actor_name = actor_rec_info.get('actor')
            genre = actor_rec_info.get('genre')
            if genre:
                converted_query = f"Which {genre} movies has {actor_name} as cast member?"
            else:
                converted_query = f"Which movies has {actor_name} as cast member?"
            print(f"[responser] Converted to factual query: {converted_query}")
            message = converted_query

        # Recommendation questions (real recs, not pseudo-factual)
        if message != original_message:
            self.last_meta['rewritten'] = message

        if is_recommendation_question(message):
            print("[responser] Detected recommendation question")
            self.last_meta['route'] = 'recommendation'
            get_linker(graph, _ent_to_lbl)  # seed titles are linked through it
            rec_result, rec_error = self._generate_recommendation_response(
                message, graph, precomputed_titles=seed_titles_hint, language_filter=language_pref
            )
            rec_time = time.time() - start_time
            print(f"[responser] Recommendation query took {rec_time:.3f}s")

            if rec_result:
                return rec_result
            else:
                return rec_error or "Could not generate recommendations."

        # Factual: either normal or language-based branch (intent first, see design.md section 2)
        self.last_meta['route'] = 'factual'
        intent = None
        linked = None  # first sub-question's result from the intent path
        if language_qid:
            print(f"[responser] Processing language-based query with QID: {language_qid}")
            factual_result, entity_found, factual_error = self._generate_language_based_response(
                message, graph, language_qid, lbl_to_ent
            )
        else:
            factual_start = time.time()
            factual_result = None
            # 1) intent + linker
            intent = parse_intent(message)
            if intent.kind in ("fact", "films_of") and intent.relation and intent.confidence >= USE_THRESHOLD:
                linker = get_linker(graph, _ent_to_lbl)
                factual_result, linked = self._answer_intent(
                    intent, graph, linker, _ent_to_lbl, pred_lbl_to_uri, message)
                if factual_result:
                    print(f"[responser] Answered through intent: {intent.relation} / {intent.mention}")
                    entity_found, factual_error = True, None
            # 2) the old regex path
            if not factual_result:
                factual_result, entity_found, factual_error = self._generate_factual_response(
                    message, graph, lbl_to_ent, pred_lbl_to_uri
                )
                entity_found = entity_found or bool(linked)
            factual_time = time.time() - factual_start
            print(f"[responser] Factual query took {factual_time:.3f}s")

        if factual_result:
            self._fill_subject_kind(graph, _ent_to_lbl)
            total_time = time.time() - start_time
            print(f"[responser] Total response time: {total_time:.3f}s")
            return factual_result

        # A character or series has no value of its own: no embedding guess for it
        if linked and linked['kind'] in VIA_FILMS_KINDS:
            self._note_linked(intent, linked)
            total_time = time.time() - start_time
            print(f"[responser] Total response time: {total_time:.3f}s")
            label = linked['cand'].label
            if linked['via_films']:
                return (f"{label} is not a film itself; the graph links it to {len(linked['via_films'])} "
                        f"film{'s' if len(linked['via_films']) != 1 else ''}, but none of them has a "
                        f"{linked['relation']} in the graph.")
            return f"{label} is not a film itself, and the graph links it to no film."

        embeddings_available = self.entity_embeds is not None and self.relation_embeds is not None

        if not embeddings_available:
            if linked:
                self._note_linked(intent, linked)
            self._fill_subject_kind(graph, _ent_to_lbl)
            total_time = time.time() - start_time
            print(f"[responser] Total response time: {total_time:.3f}s")
            if entity_found:
                return factual_error or "Could not generate a factual answer."
            else:
                print("[responser] Entity not found in KG, embeddings not available")
                return "Could not find the entity in the knowledge graph. Please rephrase your question."

        if entity_found:
            print("[responser] KG entity found but no factual answer, trying embedding-based approach")
        else:
            print("[responser] Entity not found in KG, trying embedding-based approach")

        self.last_meta['route'] = 'prediction'
        # Head entity from the linker when it linked something; else the old title lookup
        head = (linked['entity_uri'], linked['cand'].label) if linked else None
        head_rel = linked['relation'] if linked else None
        if linked:
            self._note_linked(intent, linked)
        embedding_start = time.time()
        embedding_result, entity_type, embedding_error = self._generate_embedding_response(
            message, graph, _ent_to_lbl, lbl_to_ent, pred_lbl_to_uri, head=head, rel_label=head_rel
        )
        embedding_time = time.time() - embedding_start
        print(f"[responser] Embedding query took {embedding_time:.3f}s")
        self._fill_subject_kind(graph, _ent_to_lbl)

        if embedding_result:
            total_time = time.time() - start_time
            print(f"[responser] Total response time: {total_time:.3f}s")
            note = ("as the exact entity was not found in the knowledge graph."
                    if not entity_found
                    else "because no factual answer was available in the knowledge graph.")

            entity_type_str = f" (type: {entity_type})" if entity_type else ""
            rel_label = head_rel or parse_relation(message)
            final_answer = f"{embedding_result}{entity_type_str}"

            formatted = None
            if rel_label:
                try:
                    formatted = self._format_natural_answer(
                        rel_label, [final_answer], head[1] if head else extract_title(message))
                except KeyError:
                    formatted = None
            if formatted:
                return f"{formatted} (Note: This is a prediction based on similar movies, {note})"

            return f"{final_answer} (Note: This is a prediction based on embeddings, {note})"

        total_time = time.time() - start_time
        print(f"[responser] Total response time: {total_time:.3f}s")
        if embedding_error:
            return embedding_error
        return "Could not generate an answer. Please rephrase your question in a simple way."

    def _note_linked(self, intent, linked):
        """Metadata of the subject the intent path linked, when it gave no answer itself."""
        c = linked['cand']
        self.last_meta.update(
            entity_uri=c.uri, relation=linked['relation'], property_uri=linked['property_uri'],
            inverse=linked['inverse'], intent=intent.to_dict() if intent else None,
            subject_kind=c.kind, via_films=list(linked['via_films']), answer_uris=[],
            alternatives=[{'uri': a.uri, 'qid': a.qid, 'label': a.label, 'year': a.year, 'kind': a.kind}
                          for a in linked['alternatives']],
        )

    def _fill_subject_kind(self, graph, ent_to_lbl):
        """subject_kind for answers that did not come through the intent path."""
        uri = self.last_meta.get('entity_uri')
        if uri and not self.last_meta.get('subject_kind'):
            try:
                self.last_meta['subject_kind'] = get_linker(graph, ent_to_lbl).kind_of(uri)
            except Exception:
                self.last_meta['subject_kind'] = None
