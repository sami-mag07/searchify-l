"""Optional cloud backends: Google results via Serper, and Tavily as a safety net.

Both are off by default. Serper only runs when SERPER_API_KEY is set, as an
optional fallback when you want Google coverage. Tavily only runs when
TAVILY_API_KEY is set, and then only after every other backend came back empty.
The local backends (DuckDuckGo, SearXNG) need no key and are the default.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import httpx

from ..config import get_settings
from ._common import COUNTRY_FOR_LANG, SearchBackendError, dedupe_and_filter, site_scoped


def serper_search(
    query: str,
    max_results: int = 10,
    *,
    topic: str = "general",
    language: Optional[str] = None,
    country: Optional[str] = None,
    time_range: Optional[str] = None,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    **_: object,
) -> List[Dict[str, str]]:
    """Google results via Serper (SERPER_API_KEY from the environment)."""
    settings = get_settings()
    if not settings.serper_api_key:
        raise SearchBackendError("SERPER_API_KEY is not set (set it only via the environment).")

    body: Dict[str, object] = {
        "q": site_scoped(query, include_domains),
        "num": 10 if max_results <= 10 else 20,
    }
    if language:
        body["hl"] = language
    gl = country or COUNTRY_FOR_LANG.get(language or "")
    if gl:
        body["gl"] = gl
    if time_range:
        body["tbs"] = {"day": "qdr:d", "week": "qdr:w", "month": "qdr:m", "year": "qdr:y"}.get(time_range, "")
    endpoint = "news" if topic == "news" else "search"

    try:
        with httpx.Client(timeout=settings.fetch_timeout) as client:
            resp = client.post(
                f"https://google.serper.dev/{endpoint}",
                json=body,
                headers={"X-API-KEY": settings.serper_api_key},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:120] if exc.response is not None else ""
        raise SearchBackendError(f"Serper error {exc.response.status_code}: {detail}") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise SearchBackendError(f"Serper unreachable: {type(exc).__name__}") from exc

    items = data.get("news" if topic == "news" else "organic", [])
    hits = [
        {
            "title": (it.get("title") or "").strip(),
            "url": (it.get("link") or "").strip(),
            "content": (it.get("snippet") or "").strip(),
            "engine": "serper",
        }
        for it in items
    ]
    return dedupe_and_filter(hits, exclude_domains or [], max_results, include_domains)


TAVILY_URL = "https://api.tavily.com"


def tavily_post(path: str, body: Dict[str, object], timeout: float) -> Dict:
    """POST to the Tavily API with TAVILY_API_KEY from the environment."""
    settings = get_settings()
    if not settings.tavily_api_key:
        raise SearchBackendError("TAVILY_API_KEY is not set (set it only via the environment).")
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                f"{TAVILY_URL}/{path}",
                json=body,
                headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        # Status only: Tavily error bodies may echo the request.
        raise SearchBackendError(f"Tavily error {exc.response.status_code}") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise SearchBackendError(f"Tavily unreachable: {type(exc).__name__}") from exc


def tavily_search(
    query: str,
    max_results: int = 10,
    *,
    topic: str = "general",
    time_range: Optional[str] = None,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    end_date: Optional[str] = None,
    **_: object,
) -> List[Dict[str, str]]:
    """Tavily search, the last safety net (TAVILY_API_KEY from the environment)."""
    body: Dict[str, object] = {
        "query": query,
        "max_results": min(max(max_results, 1), 20),
        "topic": "news" if topic == "news" else "general",
    }
    if time_range in ("day", "week", "month", "year"):
        body["time_range"] = time_range
    if end_date:  # YYYY-MM-DD: only pages Tavily dates on or before this day (replaying an older research)
        body["end_date"] = end_date
    if include_domains:
        body["include_domains"] = include_domains
    if exclude_domains:
        body["exclude_domains"] = exclude_domains

    data = tavily_post("search", body, get_settings().fetch_timeout)
    hits = [
        {
            "title": (it.get("title") or "").strip(),
            "url": (it.get("url") or "").strip(),
            "content": (it.get("content") or "").strip(),
            "engine": "tavily",
        }
        for it in data.get("results", [])
    ]
    return dedupe_and_filter(hits, exclude_domains or [], max_results, include_domains)
