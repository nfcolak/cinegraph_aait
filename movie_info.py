#!/usr/bin/env python3
"""
Simple utility to get detailed information about a movie from the graph.
Usage: python movie_info.py "Movie Title"
"""

import sys
from rdflib.namespace import RDFS
import rdflib

from core.data import load_graph
from core.recommender import resolve_movie_uri


def get_movie_info(graph, title: str):
    """Get detailed information about a movie."""
    # Resolve movie URI
    movie_uri = resolve_movie_uri(graph, title)

    if not movie_uri:
        print(f"Movie not found: {title}")
        return

    print(f"\n{'='*60}")
    print(f"Movie: {title}")
    print(f"URI: {movie_uri}")
    print(f"{'='*60}\n")

    # Define properties to check
    properties = {
        'P31':  'Instance of (Type)',
        'P136': 'Genre',
        'P57':  'Director',
        'P58':  'Screenwriter',
        'P161': 'Cast member',
        'P86':  'Composer',
        'P272': 'Production company',
        'P495': 'Country of origin',
        'P577': 'Publication date',
        'P2487': 'IMDb rating',
        'P364': 'Original language',
    }

    for prop_id, prop_name in properties.items():
        prop_uri = rdflib.URIRef(f'http://www.wikidata.org/prop/direct/{prop_id}')
        values = []

        for obj in graph.objects(movie_uri, prop_uri):
            # Try to get label if it's a URI
            if isinstance(obj, rdflib.URIRef):
                label = None
                for lbl in graph.objects(obj, RDFS.label):
                    label = str(lbl)
                    break
                values.append(label if label else str(obj))
            else:
                # It's a literal (date, number, etc.)
                values.append(str(obj))

        if values:
            print(f"{prop_name}:")
            for val in values[:5]:  # Limit to first 5 to avoid spam
                print(f"  - {val}")
            if len(values) > 5:
                print(f"  ... and {len(values) - 5} more")
            print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python movie_info.py 'Movie Title'")
        print("Example: python movie_info.py 'Frozen'")
        sys.exit(1)

    movie_title = " ".join(sys.argv[1:])

    print("Loading graph...")
    graph = load_graph()

    get_movie_info(graph, movie_title)