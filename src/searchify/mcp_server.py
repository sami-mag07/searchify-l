"""Searchify as an MCP server, for Claude Code, Cursor, Codex or any MCP client.

With TAVILY_API_KEY set it runs "Searchify for Tavily": Tavily searches and extracts, Searchify ranks
the passages on your machine and takes over any call where Tavily is too slow. Without a key it runs
Searchify on its own, keyless.

    searchify-mcp                       # stdio, for local clients
    searchify-mcp --http --port 8765    # streamable HTTP, for a hosted endpoint

Needs the extra: pip install "searchify[mcp,rerank]".
"""
from __future__ import annotations

import argparse
from typing import Dict, List

from mcp.server.mcpserver import MCPServer

from . import complement

CONTENT_CHARS = 4000  # per page, so a tool result stays small enough for any model


def build() -> MCPServer:
    mode = "Searchify for Tavily" if complement.has_tavily() else "Searchify"
    server = MCPServer(
        "searchify-tavily" if complement.has_tavily() else "searchify",
        instructions=(f"{mode}: web search, clean page reading and passage ranking. Use `research` for a "
                      "question that needs sources, `search` to find pages, `read` to get a page's text."),
    )

    @server.tool(description="Search the web. Returns titles, addresses, snippets and which engine answered.")
    def search(query: str, max_results: int = 8) -> Dict:
        hits, info = complement.search(query, max(1, min(max_results, 20)))
        return {"results": hits, "timing": info, "mode": mode}

    @server.tool(description="Read web pages and return their clean text (up to 20 addresses).")
    def read(urls: List[str]) -> Dict:
        docs, info = complement.extract(urls[:20])
        return {"pages": [{"url": d.get("url"), "title": d.get("title", ""),
                           "content": (d.get("content") or "")[:CONTENT_CHARS], "source": d.get("source", "searchify")}
                          for d in docs], "timing": info, "mode": mode}

    @server.tool(description="Answer a research question with sources: searches, reads the top pages and "
                             "returns the best passage from each source, ranked on this machine.")
    def research(question: str, top_k: int = 5) -> Dict:
        return complement.research(question, top_k=max(1, min(top_k, 10)))

    return server


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--http", action="store_true", help="serve streamable HTTP instead of stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    o = ap.parse_args()
    server = build()
    if o.http:
        server.run("streamable-http", host=o.host, port=o.port)
    else:
        server.run("stdio")


if __name__ == "__main__":
    main()
