#!/usr/bin/env python3
"""
Test script for multimedia query detection (overall)
"""

import re

# Global multimedia patterns
_MULTIMEDIA_PATTERNS = [
    # 1. Explicit Image Requests
    r'\b(?:show|give|display|see|view|want|find)\s+(?:me\s+)?(?:a\s+|an\s+|the\s+)?(?:picture|image|photo|pic|poster|shot|frame|still)s?\b',
    r'^(?:picture|image|photo|pic|poster|shot|frame|still)s?\s+(?:of|from|for|with|featuring)\b',
    r'\bimage\s+of\b',

    # 2. "Look Like" Queries
    r'\b(?:what|how)\s+(?:does|do|did|can|could|would)?\s*(?:.+)\s+looks?\s*(?:like)?\b',
    r'\blooks?\s+like\b',

    # 3. Direct "Show me [Entity]"
    r'\b(?:show|display|see|view)\s+(?:me\s+)?([A-Z][a-zA-Z0-9\-\.]+(?:\s+[A-Z][a-zA-Z0-9\-\.]+)*)\s*[\.\?!]?$',
    r'\blet\s+me\s+see\s+([A-Z][a-zA-Z0-9\-\.]+(?:\s+[A-Z][a-zA-Z0-9\-\.]+)*)\s*[\.\?!]?$',

    # 4. Specific Backdrops/Scenes - VERY RESTRICTIVE
    r'\bscene\s+from\b',
    r'\bin\s+a\s+scene\b',
]

def is_multimedia_query(text: str) -> bool:
    """Detect if the question is asking for a picture/image."""
    query_lower = text.lower().strip()

    # Check if user is asking for "movies" generally (Factual) vs "picture of movie" (Multimedia)
    if re.search(r'\b(?:show|list|recommend)\s+(?:me\s+)?(?:some\s+)?(?:movies?|films?)\b', query_lower):
         if not re.search(r'\b(?:poster|picture|image|photo)\b', query_lower):
             return False

    for pattern in _MULTIMEDIA_PATTERNS:
        if re.search(pattern, query_lower):
            return True
    return False

# Test queries
test_cases = [
    # Should be multimedia (TRUE)
    ("Show me a scene from Interstellar", True),
    ("Show me Brad Pitt in a scene from Fight Club", True),
    ("Show me Zendaya in a scene", True),
    ("Show me a picture of Brad Pitt", True),
    ("What does Brad Pitt look like", True),
    ("Show me the poster for Interstellar", True),
    ("Image of Anne Hathaway", True),
    # Note: "Show me [Name]" without explicit image keywords relies on entity resolution
    # in the actual system, so not tested here in pattern-only tests

    # Should NOT be multimedia (FALSE)
    ("Who directed Fight Club", False),
    ("Show me movies from 1999", False),  # "show me movies" without picture/poster
    ("Tell me about the scene in Fight Club", False),
    ("What is the opening scene of Inception", False),
    ("Recommend me some movies", False),
    ("Which movies did Christopher Nolan direct", False),
    ("Show me movies like Inception", False),  # recommendation, not image
]

print("Testing Multimedia Query Detection\n" + "="*50)
all_passed = True

for query, expected in test_cases:
    result = is_multimedia_query(query)
    status = "✓ PASS" if result == expected else "✗ FAIL"
    if result != expected:
        all_passed = False
    print(f"{status}: '{query}'")
    print(f"         Expected: {expected}, Got: {result}\n")

print("="*50)
if all_passed:
    print("✓ All tests passed!")
else:
    print("✗ Some tests failed!")
