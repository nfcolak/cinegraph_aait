# data.py
# Local graph loader and lightweight lookup builders (English labels only).

import os
import json
from typing import Dict, List, Tuple, Optional

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDFS
from collections import defaultdict
import numpy as np


# Project root and default graph path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GRAPH = os.path.join(ROOT, "data", "graph.nt")

# --- EMBEDDING PATHS ---
EMBEDDINGS_DIR = os.path.join(ROOT, "data", "embeddings")
ENTITY_EMBEDS_PATH = os.path.join(EMBEDDINGS_DIR, "entity_embeds.npy")
ENTITY_IDS_PATH = os.path.join(EMBEDDINGS_DIR, "entity_ids.del")
RELATION_EMBEDS_PATH = os.path.join(EMBEDDINGS_DIR, "relation_embeds.npy")
RELATION_IDS_PATH = os.path.join(EMBEDDINGS_DIR, "relation_ids.del")

# --- RATING PATHS ---
RATINGS_DIR = os.path.join(ROOT, "data", "ratings")
ITEM_RATINGS_PATH = os.path.join(RATINGS_DIR, "item_ratings.csv")

# --- MULTIMEDIA PATHS ---
MULTIMEDIA_DIR = os.path.join(ROOT, "data", "images")
# Mapping file for IMDb IDs -> image paths
IMAGE_MAP_PATH = os.path.join(ROOT, "data", "additional", "images.json")

# Namespaces (used only for URI/QID parsing; no external calls)
WD = Namespace("http://www.wikidata.org/entity/")
WDT = Namespace("http://www.wikidata.org/prop/direct/")

# Optional patch file with extra triples (easy to extend without editing the full graph)
PATCH_FILE = os.path.join(ROOT, "data", "graph_patch.nt")

# Minimal patch triples for missing critical facts/labels in the shipped graph
# Built-in triples to patch in before the optional patch file (keep empty by default)
EXTRA_GRAPH_TRIPLES = []


def load_graph() -> Graph:
    """
    Load the local RDF graph from GRAPH_FILE env or ./data/graph.nt.
    Supports .nt (default) and .ttl/.turtle.
    """
    graph_file = os.environ.get("GRAPH_FILE", DEFAULT_GRAPH)
    g = Graph()

    if graph_file.endswith((".ttl", ".turtle")):
        g.parse(graph_file, format="turtle")
    else:
        g.parse(graph_file, format="nt")

    # Apply local patch triples (avoids editing large graph files by hand)
    for triple in EXTRA_GRAPH_TRIPLES:
        g.add(triple)

    # Apply user-provided patch triples if the optional patch file exists
    if os.path.exists(PATCH_FILE):
        patch_graph = Graph()
        patch_graph.parse(PATCH_FILE, format="nt")
        added = 0
        for triple in patch_graph:
            if triple not in g:
                g.add(triple)
                added += 1
        print(f"[graph] applied {added} triples from {PATCH_FILE}")

    print(f"[graph] loaded {len(g)} triples from {graph_file}")
    return g


# --- To load embeddings ---
def load_embeddings():
    """
    Load KGE embeddings and create lookup maps.
    """
    try:
        # Load embedding matrices
        entity_embeds = np.load(ENTITY_EMBEDS_PATH)
        relation_embeds = np.load(RELATION_EMBEDS_PATH)

        # Load ID to URI mappings
        ent_uri_to_id: Dict[str, int] = {}
        id_to_ent_uri: Dict[int, str] = {}

        with open(ENTITY_IDS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) != 2:
                    continue

                uri, _id_str = parts[0], parts[1]

                try:
                    _id = int(_id_str)
                    ent_uri_to_id[uri] = _id
                    id_to_ent_uri[_id] = uri
                except ValueError:
                    try:
                        _id = int(uri)
                        uri = _id_str
                        ent_uri_to_id[uri] = _id
                        id_to_ent_uri[_id] = uri
                    except ValueError:
                        continue

        rel_uri_to_id: Dict[str, int] = {}
        with open(RELATION_IDS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) != 2:
                    continue

                uri, _id_str = parts[0], parts[1]

                try:
                    _id = int(_id_str)
                    rel_uri_to_id[uri] = _id
                except ValueError:
                    try:
                        _id = int(uri)
                        uri = _id_str
                        rel_uri_to_id[uri] = _id
                    except ValueError:
                        continue

        return entity_embeds, relation_embeds, ent_uri_to_id, rel_uri_to_id, id_to_ent_uri

    except Exception as e:
        print(f"[embeddings] Failed to load embeddings: {e}")
        raise e


# Cache for label maps to avoid rebuilding on every request
_label_maps_cache = None


def build_label_maps(g: Graph, use_cache: bool = True):
    """
    Build lightweight lookup maps: ent_to_lbl, lbl_to_ent, pred_lbl_to_uri.
    """
    global _label_maps_cache

    if use_cache and _label_maps_cache is not None:
        return _label_maps_cache

    print("[data] Building label maps (this may take a moment)...")

    ent_to_lbl: Dict[URIRef, str] = {}
    ent_label_lang: Dict[URIRef, Optional[str]] = {}
    for s, o in g.subject_objects(RDFS.label):
        lang = getattr(o, "language", None)
        if lang not in (None, "en"):
            continue

        prev_lang = ent_label_lang.get(s)

        # Prefer explicit English labels over language-less ones, and avoid
        # overriding an existing English label with a noisier option.
        if prev_lang == "en":
            if lang != "en":
                continue
        elif lang == "en" or prev_lang is None:
            ent_label_lang[s] = lang or None
        else:
            continue

        ent_to_lbl[s] = str(o)

    lbl_to_ent_multi: Dict[str, List[URIRef]] = defaultdict(list)
    for uri, label in ent_to_lbl.items():
        lbl_to_ent_multi[label].append(uri)

    ratings_map = load_ratings(use_cache=True)
    lbl_to_ent: Dict[str, URIRef] = {}

    for label, uris in lbl_to_ent_multi.items():
        if len(uris) == 1:
            lbl_to_ent[label] = uris[0]
        else:
            p31 = URIRef("http://www.wikidata.org/prop/direct/P31")
            film = URIRef("http://www.wikidata.org/entity/Q11424")

            def score_uri(u: URIRef):
                is_film = (u, p31, film) in g
                rating = ratings_map.get(str(u), 0.0)
                return (is_film, rating if is_film else -10.0)

            uris.sort(key=score_uri, reverse=True)
            lbl_to_ent[label] = uris[0]

    pred_lbl_to_uri: Dict[str, URIRef] = {}
    predicates = set(g.predicates())

    for p in predicates:
        for lbl_obj in g.objects(p, RDFS.label):
            lang = getattr(lbl_obj, "language", None)
            if lang in (None, "en"):
                pred_lbl_to_uri[str(lbl_obj).lower()] = p
                break

    result = (ent_to_lbl, lbl_to_ent, pred_lbl_to_uri)

    if use_cache:
        _label_maps_cache = result
        print(f"[data] Label maps built and cached: {len(ent_to_lbl)} entities.")

    return result


# Cache for ratings
_ratings_cache = None


def load_ratings(use_cache: bool = True) -> Dict[str, float]:
    """
    Load movie ratings from CSV file.
    """
    global _ratings_cache

    if use_cache and _ratings_cache is not None:
        return _ratings_cache

    print("[data] Loading movie ratings...")
    ratings: Dict[str, float] = {}

    try:
        import csv

        with open(ITEM_RATINGS_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                uri = row["item_id"]
                rating = float(row["rating"])
                ratings[uri] = rating

        if use_cache:
            _ratings_cache = ratings
        return ratings

    except Exception as e:
        print(f"[data] Error/Warning loading ratings: {e}")
        return {}


# Cache for the loaded image map
_IMAGE_MAP_CACHE: Optional[Dict[str, Dict[str, str]]] = None


def load_image_map(use_cache: bool = True) -> Dict[str, Dict[str, str]]:
    """
    Loads image mappings categorized by type.
    Returns structure:
    {
        'profile': { 'nm_id': 'path.jpg' },        # Person queries
        'poster':  { 'tt_id': 'path.jpg' },        # Movie poster queries
        'backdrop': { 'tt_id': 'path.jpg' },       # Scene queries (Movie-based)
        'backdrop_cast': { 'nm_id': 'path.jpg' }   # Scene queries (Actor-based)
    }
    """
    global _IMAGE_MAP_CACHE
    
    if use_cache and _IMAGE_MAP_CACHE is not None:
        return _IMAGE_MAP_CACHE

    print(f"[data] Loading image map from: {IMAGE_MAP_PATH}")
    
    try:
        with open(IMAGE_MAP_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Initialize separate maps
        combo_count = 0
        maps = {
            'profile': {},
            'poster': {},
            'backdrop': {},        # Maps Movie ID -> Image
            'backdrop_cast': {},   # Maps Actor ID -> Image (New!)
            # Actor -> (Movie -> Backdrop) lookup so we can answer
            # "Actor in a scene from Movie" without re-reading the huge JSON.
            'backdrop_actor_movie': {},
        }

        for item in data:
            image_path = item.get("img")
            cast_ids = item.get("cast", [])
            movie_ids = item.get("movie", [])
            img_type = item.get("type")

            if not image_path: continue

            # 1. PROFILE IMAGES (Person -> Headshot)
            if img_type == 'profile' or img_type == 'cast':
                for nm_id in cast_ids:
                    if nm_id not in maps['profile']:
                        maps['profile'][nm_id] = image_path

            # 2. POSTER IMAGES (Movie -> Poster)
            elif img_type == 'poster':
                for tt_id in movie_ids:
                    if tt_id not in maps['poster']:
                        maps['poster'][tt_id] = image_path
                
            # 3. BACKDROP IMAGES (Movie -> Scene/Still AND Actor -> Scene)
            elif img_type == 'backdrop':
                # Map for Movie ID (e.g., "Scene from Interstellar")
                for tt_id in movie_ids:
                    if tt_id not in maps['backdrop']:
                        maps['backdrop'][tt_id] = image_path
                
                # Map for Cast ID (e.g., "Zendaya in a scene")
                for nm_id in cast_ids:
                    if nm_id not in maps['backdrop_cast']:
                        maps['backdrop_cast'][nm_id] = image_path
                    
                    if movie_ids:
                        movie_lookup = maps['backdrop_actor_movie'].setdefault(nm_id, {})
                        for tt_id in movie_ids:
                            if tt_id not in movie_lookup:
                                movie_lookup[tt_id] = image_path
                                combo_count += 1

        _IMAGE_MAP_CACHE = maps
        print(
            "[data] Loaded Maps - Profiles: {0}, Posters: {1}, Backdrops (Movie): {2}, "
            "Backdrops (Cast): {3}, Backdrop Actor+Movie combos: {4}".format(
                len(maps['profile']),
                len(maps['poster']),
                len(maps['backdrop']),
                len(maps['backdrop_cast']),
                combo_count,
            )
        )
        return maps
        
    except Exception as e:
        print(f"[data ERROR] Error loading image map: {e}")
        return {}
