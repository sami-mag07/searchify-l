# Searchify for Tavily

Two editions from one package:

| Edition | Who does what | Key |
|---|---|---|
| **Searchify** (main, unchanged) | Searchify searches, reads and ranks; Tavily only as the last safety net if a key is set | none |
| **Searchify for Tavily** (`searchify.complement`) | Tavily searches and extracts; Searchify ranks every passage on your machine and takes over any call where Tavily is slower than its budget | your `TAVILY_API_KEY` |

The take-over: Tavily gets `SEARCHIFY_TAVILY_BUDGET` seconds for a search (default 3) and
`SEARCHIFY_EXTRACT_BUDGET` for an extraction (default 5). If it has not answered by then, Searchify's own
search or reader starts in parallel and the first answer wins. Pages Tavily could not read go to
Searchify's reader. `timing` in every result says who did each step.

## Try it

| Surface | Without a key | With a Tavily key |
|---|---|---|
| Claude Code plugin | `/plugin marketplace add sami-mag07/searchify-l` then `/plugin install searchify@searchify` | `/plugin install searchify-tavily@searchify` (reads `TAVILY_API_KEY` from your environment) |
| Agent Skill (Claude Code, Codex, Cursor, ...) | `npx skills add sami-mag07/searchify-l --skill searchify` | `npx skills add sami-mag07/searchify-l --skill searchify-tavily` |
| MCP server (any client) | `claude mcp add searchify -e SEARCHIFY_MODE=local -- uvx --from "searchify[mcp,rerank] @ git+https://github.com/sami-mag07/searchify-l@tavily-edition" searchify-mcp` | same with `-e TAVILY_API_KEY=$TAVILY_API_KEY` instead |
| Command line | `SEARCHIFY_MODE=local searchify research "question"` | `searchify research "question"` |
| Hosted MCP (HTTP) | `searchify-mcp --http --port 8765` | same, with the key in the server's environment |
