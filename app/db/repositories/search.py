"""
Helpers for building safe PostgREST search filters.
"""

import re

# Characters that are LIKE wildcards or cannot be safely quoted in a PostgREST value
_UNSAFE_CHARS = re.compile(r'[%*_\\"]')
MAX_SEARCH_LENGTH = 100


def clean_search_term(term: str | None) -> str:
    """Normalise user search input; returns '' when nothing searchable is left."""
    if not term:
        return ""
    cleaned = _UNSAFE_CHARS.sub(" ", term)
    cleaned = " ".join(cleaned.split())
    return cleaned[:MAX_SEARCH_LENGTH]


def build_ilike_or_filter(columns: list[str], term: str) -> str:
    """
    Build an `or=(...)` filter matching `term` against several columns.

    Each value is double-quoted so commas, dots, parentheses and colons in the
    search term are treated as literal text instead of PostgREST syntax.
    Callers must pass a term already processed by clean_search_term.
    """
    return ",".join(f'{col}.ilike."%{term}%"' for col in columns)
