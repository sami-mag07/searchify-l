"""Searchify for Tavily: the two work together instead of one replacing the other.

Tavily does the external work: web search and page extraction. Searchify does the internal work on
your machine: cutting pages into passages, ranking them for the question, and returning the best
passage per source. When Tavily answers within a latency budget, its result is used. When it takes
longer, Searchify's own search or extraction starts in parallel and whichever answers first wins,
so a slow call never blocks the agent.

    from searchify.complement import research
    research("How much memory does the NVIDIA DGX Spark have?")

Without TAVILY_API_KEY everything runs on Searchify's own stages, exactly like the main package.

Environment:
    TAVILY_API_KEY              your Tavily key (only read from the environment)
    SEARCHIFY_TAVILY_BUDGET     seconds Tavily gets for a search before Searchify joins (default 3)
    SEARCHIFY_EXTRACT_BUDGET    seconds Tavily gets for an extraction before Searchify joins (default 5)
    SEARCHIFY_MODE=local        Searchify only, never Tavily (used by the keyless plugin)
"""
from __future__ import annotations

import os
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Callable, Dict, List, Optional, Tuple

from .config import get_settings
from .extract.reader import read_pages
from .search import BACKENDS, _chain
from .search._common import SearchBackendError
from .search.cloud import tavily_post, tavily_search

_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="searchify-complement")
_RANK_LOCK = threading.Lock()  # the ranking model is not safe to call from several threads at once (MPS crashes)


def _budget(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def local_only() -> None:
    """SEARCHIFY_MODE=local: never call Tavily, even if a key is in the environment (the keyless plugin)."""
    if os.environ.get("SEARCHIFY_MODE", "").lower() == "local":
        os.environ.pop("TAVILY_API_KEY", None)


local_only()


def has_tavily() -> bool:
    return bool(get_settings().tavily_api_key)


def _race(primary: Callable[[], List], backup: Callable[[], List], budget: float) -> Tuple[List, str, float]:
    """Run `primary` (Tavily); if it has not answered within `budget` seconds, or fails, start `backup`
    (Searchify) as well. Return the first non-empty answer, which side gave it, and the seconds taken."""
    t0 = time.perf_counter()
    first = _POOL.submit(primary)
    done, _ = wait([first], timeout=budget)
    if done:
        try:
            result = first.result()
            if result:
                return result, "tavily", time.perf_counter() - t0
        except Exception:  # noqa: BLE001 - a failed call hands over to Searchify
            pass
        result = backup()
        return result, "searchify", time.perf_counter() - t0
    second = _POOL.submit(backup)
    pending = {first: "tavily", second: "searchify"}
    while pending:
        done, _ = wait(list(pending), return_when=FIRST_COMPLETED)
        for fut in done:
            side = pending.pop(fut)
            try:
                result = fut.result()
            except Exception:  # noqa: BLE001
                continue
            if result:
                return result, f"{side} (Tavily over budget)" if side == "searchify" else "tavily (late)", \
                    time.perf_counter() - t0
    return [], "none", time.perf_counter() - t0


def _local_search(query: str, max_results: int, **filters) -> List[Dict[str, str]]:
    filters.pop("end_date", None)  # date limits are a Tavily feature; the local backends don't take them
    for name in _chain():
        if name == "tavily":
            continue
        try:
            hits = BACKENDS[name](query, max_results, **filters)
            if hits:
                return hits
        except SearchBackendError:
            continue
    return []


def search(query: str, max_results: int = 10, **filters) -> Tuple[List[Dict[str, str]], Dict]:
    """Web search: Tavily first within the budget, Searchify's keyless search when Tavily is slow."""
    if not has_tavily():
        t0 = time.perf_counter()
        hits = _local_search(query, max_results, **filters)
        return hits, {"search_by": "searchify", "search_s": round(time.perf_counter() - t0, 2)}
    hits, side, took = _race(lambda: tavily_search(query, max_results, **filters),
                             lambda: _local_search(query, max_results, **filters),
                             _budget("SEARCHIFY_TAVILY_BUDGET", 3.0))
    return hits, {"search_by": side, "search_s": round(took, 2)}


def _tavily_extract(urls: List[str], fmt: str) -> List[Dict]:
    data = tavily_post("extract", {"urls": urls[:20], "format": fmt}, get_settings().fetch_timeout)
    return [{"url": r.get("url"), "title": r.get("title") or "", "content": r.get("raw_content") or "",
             "source": "tavily"} for r in data.get("results", []) if r.get("raw_content")]


def extract(urls: List[str], fmt: str = "markdown") -> Tuple[List[Dict], Dict]:
    """Page text: Tavily Extract first within the budget; pages it misses, or a slow call, go to Searchify."""
    urls = list(urls)
    if not has_tavily():
        t0 = time.perf_counter()
        docs, _ = read_pages(urls, fmt, None)
        return docs, {"extract_by": "searchify", "extract_s": round(time.perf_counter() - t0, 2)}
    docs, side, took = _race(lambda: _tavily_extract(urls, fmt), lambda: read_pages(urls, fmt, None)[0],
                             _budget("SEARCHIFY_EXTRACT_BUDGET", 5.0))
    got = {d.get("url") for d in docs}
    missing = [u for u in urls if u not in got]
    if missing and side.startswith("tavily"):  # pages Tavily could not read: Searchify's own reader
        more, _ = read_pages(missing, fmt, None)
        docs = docs + more
        side = f"{side} + searchify for {len(more)} page(s)"
    return docs, {"extract_by": side, "extract_s": round(took, 2)}


def research(question: str, max_results: int = 8, read: int = 5, top_k: int = 5, **filters) -> Dict:
    """Search, read the top pages, rank every passage on this machine, return the best per source."""
    from .rerank import rerank  # optional extra: searchify[rerank]
    as_of = os.environ.get("SEARCHIFY_AS_OF")
    if as_of and "end_date" not in filters:
        filters["end_date"] = as_of
    hits, s_info = search(question, max_results, **filters)
    docs, e_info = extract([h["url"] for h in hits[:read]]) if hits else ([], {"extract_by": "none", "extract_s": 0})
    passages = [{"content": p, "url": d["url"], "title": d.get("title", "")}
                for d in docs for p in (d.get("content") or "").split("\n") if len(p.split()) >= 12]
    t0 = time.perf_counter()
    with _RANK_LOCK:
        ranked = rerank(question, passages) if passages else []
    rank_s = time.perf_counter() - t0
    best, seen = [], set()
    for p in ranked:  # one passage per source
        if p["url"] not in seen:
            seen.add(p["url"])
            best.append(p)
        if len(best) == top_k:
            break
    return {"question": question, "passages": best,
            "timing": {**s_info, **e_info, "rank_by": "searchify (on this machine)", "rank_s": round(rank_s, 2)},
            "mode": "searchify + tavily" if has_tavily() else "searchify"}


__all__ = ["search", "extract", "research", "has_tavily"]
