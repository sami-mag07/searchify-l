---
name: searchify-tavily
description: Web research with sources using Tavily together with Searchify. Use when a question needs current facts from the web and TAVILY_API_KEY is set. Tavily searches and extracts pages, Searchify ranks the passages on the user's machine and takes over any call where Tavily is slow.
---

# Searchify for Tavily

Tavily does the external work, web search and page extraction, with the user's own key. Searchify does
the internal work on this machine: it cuts pages into passages, ranks them for the question and returns
the best passage per source. If Tavily takes longer than its time budget for a call, Searchify's own
search or reader runs in parallel and the first answer wins, so the agent never waits on one slow call.

## Setup

Needs `TAVILY_API_KEY` in the environment (from app.tavily.com). Never print it or pass it in arguments.
Optional: `SEARCHIFY_TAVILY_BUDGET` (seconds for a search, default 3) and `SEARCHIFY_EXTRACT_BUDGET`
(seconds for an extraction, default 5).

## Use it

If the MCP tools are available (plugin `searchify-tavily`), call `research(question)`, `search(query)`
or `read(urls)`. Otherwise the command line (needs `uv`):

```bash
uvx --from "searchify[mcp,rerank] @ git+https://github.com/sami-mag07/searchify-l@tavily-edition" searchify research "your question"
```

`timing` in the output says who did what, for example `"search_by": "tavily"`,
`"extract_by": "tavily + searchify for 1 page(s)"`, `"rank_by": "searchify (on this machine)"`.

## Rules

- Answer from the returned passages and cite their URLs. If no passage supports an answer, say so.
- Prefer `research` over several `search` calls; it already reads and ranks the pages.
