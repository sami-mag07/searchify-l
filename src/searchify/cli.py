"""Command line for agents and skills: JSON on stdout.

    searchify research "How much memory does the DGX Spark have?"
    searchify search "nebius token factory regions"
    searchify read https://example.com/page

With TAVILY_API_KEY set, Tavily searches and extracts and Searchify ranks; without it, Searchify alone.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import complement


def main() -> None:
    ap = argparse.ArgumentParser(prog="searchify", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("research", help="best passage per source for a question")
    r.add_argument("question")
    r.add_argument("--top-k", type=int, default=5)
    s = sub.add_parser("search", help="web search")
    s.add_argument("query")
    s.add_argument("--max-results", type=int, default=8)
    x = sub.add_parser("read", help="clean text of web pages")
    x.add_argument("urls", nargs="+")
    for name, helptext in (("ask", "answer a question with any model, using Searchify's tools"),
                           ("chat", "chatbot in the terminal with any model, using Searchify's tools")):
        c = sub.add_parser(name, help=helptext)
        if name == "ask":
            c.add_argument("question")
        c.add_argument("--preset", default="", help="a tested model, e.g. deepseek-v4-flash or ollama:qwen3 (see `searchify models`)")
        c.add_argument("--base-url", default="", help="any OpenAI-compatible server, e.g. http://localhost:11434/v1")
        c.add_argument("--model", default="")
    sub.add_parser("models", help="list the model presets")
    o = ap.parse_args()
    if o.cmd == "models":
        from .agent import PRESETS
        for k, (url, mid, key, note) in PRESETS.items():
            print(f"{k:28s} {mid:42s} {('needs ' + key) if key else 'local'} · {note}")
        return
    if o.cmd in ("ask", "chat"):
        from . import agent
        target = agent.resolve(o.preset, o.base_url, o.model)
        if o.cmd == "chat":
            agent.chat(target)
            return
        out = agent.ask(o.question, target["base_url"], target["model"], target["api_key"],
                        log=lambda s: print(f"  · {s}", file=sys.stderr))
    elif o.cmd == "research":
        out = complement.research(o.question, top_k=o.top_k)
    elif o.cmd == "search":
        hits, info = complement.search(o.query, o.max_results)
        out = {"results": hits, "timing": info}
    else:
        docs, info = complement.extract(o.urls)
        out = {"pages": docs, "timing": info}
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
