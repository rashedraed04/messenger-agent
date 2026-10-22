"""
Simple offset pagination for dashboard list pages.

Repositories are asked for page_size + 1 rows; the extra row only signals
that a next page exists, so no COUNT query is needed.
"""

from typing import Any
from fastapi import Request

PAGE_SIZE = 25


def page_offset(page: int, page_size: int = PAGE_SIZE) -> tuple[int, int, int]:
    """Return (safe_page, offset, fetch_limit) for a 1-based page number."""
    safe_page = max(page, 1)
    return safe_page, (safe_page - 1) * page_size, page_size + 1


def paginate(
    request: Request,
    rows: list[dict[str, Any]],
    page: int,
    page_size: int = PAGE_SIZE,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Trim the look-ahead row and build prev/next links keeping current filters."""
    has_next = len(rows) > page_size

    def url_for_page(target: int) -> str:
        url = request.url.include_query_params(page=target)
        return f"{url.path}?{url.query}"

    pagination = {
        "page": page,
        "has_prev": page > 1,
        "has_next": has_next,
        "prev_url": url_for_page(page - 1) if page > 1 else None,
        "next_url": url_for_page(page + 1) if has_next else None,
    }
    return rows[:page_size], pagination
