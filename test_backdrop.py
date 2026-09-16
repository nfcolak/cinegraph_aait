#!/usr/bin/env python3
"""
Test script for backdrop query detection
"""

import re

# Backdrop patterns - VERY RESTRICTIVE
_BACKDROP_PATTERNS = [
    r'\bscene\s+from\b',  # "scene from [Movie]"
    r'\bin\s+a\s+scene\b',  # "[Actor] in a scene"
    r'\bshow\s+(?:me\s+)?(?:a\s+)?scene\b',  # "show me a scene"
]

def is_backdrop_query(text: str) -> bool:
    """Detect if the question is asking for a backdrop/scene image."""
    query_lower = text.lower().strip()
    for pattern in _BACKDROP_PATTERNS:
        if re.search(pattern, query_lower):
            return True
    return False

# Test queries
test_cases = [
    # Should be backdrop (TRUE)
    ("Show me a scene from Interstellar", True),
    ("Show me Brad Pitt in a scene from Fight Club", True),
    ("Show me Zendaya in a scene", True),
    ("scene from The Matrix", True),
    ("Can you show me a scene from Titanic?", True),

    # Should NOT be backdrop (FALSE)
    ("Show me Brad Pitt", False),
    ("Show me a picture of Brad Pitt", False),
    ("What does Brad Pitt look like", False),
    ("Show me the poster for Interstellar", False),
    ("Who directed Fight Club", False),
    ("Show me movies from 1999", False),
    ("Tell me about the scene in Fight Club", False),  # "about the scene" not "a scene from"
    ("What is the opening scene of Inception", False),  # "scene of" not "scene from"
    ("Show me Interstellar", False),
]

print("Testing Backdrop Query Detection\n" + "="*50)
all_passed = True

for query, expected in test_cases:
    result = is_backdrop_query(query)
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
