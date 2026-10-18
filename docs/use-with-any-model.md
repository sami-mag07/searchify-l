# Use Searchify with any model

Searchify gives a model three tools: `research` (best passage per source for a question), `search` and
`read`. Every surface below comes in two versions: **Searchify** (keyless) and **Searchify for Tavily**
(Tavily searches and extracts with your key, Searchify ranks the passages on your machine and takes over
any call where Tavily is slow). Set `TAVILY_API_KEY` for the second; set `SEARCHIFY_MODE=local` to force the first.

Install once (needs [uv](https://docs.astral.sh/uv/)):

```bash
uv tool install "searchify[mcp,rerank] @ git+https://github.com/sami-mag07/searchify-l@tavily-edition"
```

That gives you two commands: `searchify` (command line and chatbot) and `searchify-mcp` (MCP server).

## The models we tested

[Tryouts](https://github.com/Malek1414/tryouts) ran the same research agent across these models. Each is a
preset (`searchify models` lists them), with what our tests found it good for.

| Preset | Runs on | Tryouts finding |
|---|---|---|
| `nemotron-3.5-super-vl` | Nebius Token Factory | best on our own logs with deep mode; all 14 tool tasks |
| `deepseek-v4-flash` | Nebius Token Factory | tool-heavy agents: all 14 tool tasks at about 1/50 of Claude's cost |
| `beam` | Nebius Token Factory | multi-hop research at low cost (80% on hard questions) |
| `nemotron-super` | Nebius Token Factory | hard multi-hop research (77%) |
| `nemotron-lightning` | Nebius Token Factory | cheapest model that holds up, with thinking on |
| `nemotron-ultra` | Nebius Token Factory | needs the right tool-call parser on the server |
| `nemotron-nano`, `qwen3-30b`, `gpt-oss-120b` | Nebius Token Factory | single facts; weaker on multi-hop |
| `ollama:qwen3`, `ollama:gpt-oss` | your machine, Ollama | the same open model families, local |
| `lmstudio` | your machine, LM Studio | any model you load there |
| `llamacpp:nemotron-nano-9b` | your machine, llama.cpp | small Nemotron; see the note on tool calls below |

Token Factory presets need `NEBIUS_API_KEY`. Any other OpenAI-compatible server works with
`--base-url` and `--model`.

## Command line and chatbot

```bash
searchify ask "How much memory does the DGX Spark have?" --preset deepseek-v4-flash
searchify chat --preset ollama:qwen3                                   # chatbot in the terminal
searchify chat --base-url http://localhost:1234/v1 --model qwen/qwen3-4b   # LM Studio
searchify research "question"                                          # no model, just ranked passages
```

## Claude Code: plugins, slash commands, skills

```
/plugin marketplace add sami-mag07/searchify-l
/plugin install searchify@searchify            # keyless
/plugin install searchify-tavily@searchify     # with TAVILY_API_KEY in your environment
/searchify:research <question>                 # slash command (or /searchify-tavily:research)
```

Skills for any agent that reads Agent Skills (Claude Code, Codex, Cursor and more):

```bash
npx skills add sami-mag07/searchify-l --skill searchify
npx skills add sami-mag07/searchify-l --skill searchify-tavily
```

## MCP server, for apps that run local models

The same server for every client. Keyless:

```json
{ "mcpServers": { "searchify": { "command": "searchify-mcp", "env": { "SEARCHIFY_MODE": "local" } } } }
```

With Tavily: replace the env with `{ "TAVILY_API_KEY": "<your key>" }` and name it `searchify-tavily`.

| App | Where the config goes |
|---|---|
| LM Studio | Program tab, Install, Edit `mcp.json` (paste the block above) |
| Jan | Settings, MCP Servers, add `searchify-mcp` |
| Continue (VS Code, JetBrains) | `config.yaml` under `mcpServers` |
| Cline | MCP Servers, Configure, `cline_mcp_settings.json` |
| Goose | `goose configure`, add extension, command `searchify-mcp` |
| Claude Desktop, Cursor, Codex | their `mcpServers` config, same block |
| Open WebUI (hosts any local model as a chatbot) | run `uvx mcpo --port 8000 -- searchify-mcp`, then add `http://localhost:8000` as a tool server |

For a hosted endpoint: `searchify-mcp --http --host 0.0.0.0 --port 8765` serves streamable HTTP.

## Note on local tool calls

Small local models differ a lot in tool calling; Tryouts measured it (14 MCP tool tasks). With llama.cpp
build 9430, Nemotron Nano 9B v2 crashes the server on tool calls (grammar error); use it through Token
Factory, or a Qwen3 or gpt-oss model locally, until that is fixed upstream.
