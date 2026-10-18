---
name: searchify
description: Web research with sources, keyless. Use when a question needs current facts from the web, a page's clean text, or the best passage per source for an answer. Runs search, page reading and passage ranking on the user's machine with no API key.
---

# Searchify

Searchify searches the web, reads the top pages and ranks every paragraph against the question on
this machine, so you get the passages that answer it, with their sources. No API key.

## Use it

If the Searchify MCP tools are available (plugin `searchify`), call them:

- `research(question)` for a question that needs sources: best passage per source, ranked.
- `search(query)` to find pages, `read(urls)` to get a page's clean text.

Otherwise run the command line (needs `uv`):

```bash
SEARCHIFY_MODE=local uvx --from "searchify[mcp,rerank] @ git+https://github.com/sami-mag07/searchify-l@tavily-edition" searchify research "your question"
SEARCHIFY_MODE=local uvx --from "searchify[mcp,rerank] @ git+https://github.com/sami-mag07/searchify-l@tavily-edition" searchify read https://example.com/page
```

Output is JSON. Each passage has `content`, `url` and `rerank_score`; `timing` says what each step took.

## Rules

- Answer from the returned passages and cite their URLs. If no passage supports an answer, say so.
- Prefer `research` over several `search` calls; it already reads and ranks the pages.
- The first run downloads the ranking model (about 470 MB) once.
