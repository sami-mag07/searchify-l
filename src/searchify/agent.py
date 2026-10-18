"""Searchify for local open-source models: a small agent that gives any OpenAI-compatible model
Searchify's tools (search, read, research) through function calling.

Works with the servers people run their own models on: Ollama, LM Studio, llama.cpp (llama-server),
vLLM, Jan, or any hosted OpenAI-compatible endpoint. With TAVILY_API_KEY set, Tavily searches and
extracts and Searchify ranks; without it, Searchify alone.

    searchify ask "How much memory does the DGX Spark have?" --base-url http://localhost:11434/v1 --model qwen3:4b
    searchify ask "..." --base-url http://localhost:1234/v1 --model qwen/qwen3-4b      # LM Studio
    searchify ask "..." --base-url http://localhost:8080/v1 --model local             # llama-server

Uses only the standard library for the HTTP calls, so no extra install is needed.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from typing import Callable, Dict, List

from . import complement

SYSTEM = ("You answer questions with web research. Use the tools: `research` for a question that needs "
          "sources, `search` to find pages, `read` to get a page's text. Answer only from what the tools "
          "return, cite the source URLs, and say so if the tools found nothing.")

TOOLS = [
    {"type": "function", "function": {
        "name": "research", "description": "Search the web, read the top pages and return the best passage per source.",
        "parameters": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}}},
    {"type": "function", "function": {
        "name": "search", "description": "Search the web; returns titles, URLs and snippets.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "read", "description": "Return the clean text of web pages.",
        "parameters": {"type": "object", "properties": {"urls": {"type": "array", "items": {"type": "string"}}},
                       "required": ["urls"]}}},
]


AS_OF = os.environ.get("SEARCHIFY_AS_OF", "")  # YYYY-MM-DD: replay a research as if it were that day


def _run_tool(name: str, args: Dict) -> Dict:
    if name == "research":
        out = complement.research(str(args.get("question", "")), top_k=5)
        return {"passages": [{"content": p["content"][:900], "url": p["url"]} for p in out["passages"]],
                "timing": out["timing"]}
    if name == "search":
        hits, info = complement.search(str(args.get("query", "")), 8, **({"end_date": AS_OF} if AS_OF else {}))
        return {"results": [{"title": h["title"], "url": h["url"], "content": h["content"][:300]} for h in hits],
                "timing": info}
    if name == "read":
        urls = args.get("urls") or []
        docs, info = complement.extract([urls] if isinstance(urls, str) else urls[:5])
        return {"pages": [{"url": d.get("url"), "content": (d.get("content") or "")[:3000]} for d in docs],
                "timing": info}
    return {"error": f"unknown tool {name}"}


def _chat(base_url: str, model: str, messages: List[Dict], api_key: str) -> Dict:
    body = json.dumps({"model": model, "messages": messages, "tools": TOOLS, "temperature": 0}).encode()
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


def ask(question: str, base_url: str, model: str, api_key: str = "local", max_steps: int = 6,
        log: Callable[[str], None] = lambda _: None) -> Dict:
    """Run the tool loop; returns the final answer, the tool calls made and the time taken."""
    t0 = time.perf_counter()
    system = SYSTEM + (f" Today is {AS_OF}; treat anything after that date as unknown." if AS_OF else "")
    messages: List[Dict] = [{"role": "system", "content": system}, {"role": "user", "content": question}]
    calls = []
    for _ in range(max_steps):
        msg = _chat(base_url, model, messages, api_key)["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            answer = re.sub(r"<think>.*?</think>", "", msg.get("content") or "", flags=re.S).strip()
            if not answer:  # small local models sometimes put the whole answer in their hidden reasoning
                messages.append({"role": "user", "content": "Give your final answer now in plain text, citing the URLs."})
                again = _chat(base_url, model, messages, api_key)["choices"][0]["message"]
                answer = re.sub(r"<think>.*?</think>", "", again.get("content") or "", flags=re.S).strip() \
                    or (again.get("reasoning_content") or msg.get("reasoning_content") or "").strip()[-1500:]
            return {"answer": answer, "tool_calls": calls, "seconds": round(time.perf_counter() - t0, 1),
                    "mode": "searchify + tavily" if complement.has_tavily() else "searchify"}
        turn = {"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls}
        if msg.get("reasoning_content"):
            turn["reasoning_content"] = msg["reasoning_content"]
        messages.append(turn)
        for tc in tool_calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            log(f"{name} {json.dumps(args, ensure_ascii=False)[:120]}")
            result = _run_tool(name, args)
            calls.append({"tool": name, "args": args, "timing": result.get("timing")})
            messages.append({"role": "tool", "tool_call_id": tc.get("id", name), "content": json.dumps(result, ensure_ascii=False)})
    # Step budget used up: one last turn without tools, so the model answers from what it found.
    messages.append({"role": "user", "content": "No tool calls left. Give your final answer now from what you found, citing the URLs."})
    body = json.dumps({"model": model, "messages": messages, "temperature": 0}).encode()
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=600) as r:
        msg = json.load(r)["choices"][0]["message"]
    answer = re.sub(r"<think>.*?</think>", "", msg.get("content") or "", flags=re.S).strip() \
        or (msg.get("reasoning_content") or "").strip()[-1500:]
    return {"answer": answer, "tool_calls": calls, "seconds": round(time.perf_counter() - t0, 1),
            "mode": "searchify + tavily" if complement.has_tavily() else "searchify", "note": "answered after the step limit"}


def default_base_url() -> str:
    return os.environ.get("SEARCHIFY_LLM_BASE_URL", "http://localhost:11434/v1")  # Ollama's default


__all__ = ["ask", "TOOLS", "default_base_url"]


# The models we tested in Tryouts (github.com/Malek1414/tryouts), as presets. "nebius" runs them on
# Nebius Token Factory (NEBIUS_API_KEY); the local entries are the same open models on your own machine.
NEBIUS = os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
PRESETS = {
    # name: (base_url, model id, key env var, what Tryouts found it good for)
    "nemotron-super": (NEBIUS, "nvidia/nemotron-3-super-120b-a12b", "NEBIUS_API_KEY", "hard multi-hop research"),
    "nemotron-ultra": (NEBIUS, "nvidia/Nemotron-3-Ultra-550b-a55b", "NEBIUS_API_KEY", "long reasoning; tool calls need the right server parser"),
    "nemotron-3.5-super-vl": (NEBIUS, "nvidia/Nemotron-3.5-Super-VL", "NEBIUS_API_KEY", "best on our own logs with deep mode, all 14 tool tasks"),
    "nemotron-lightning": (NEBIUS, "nvidia/Nemotron-3_5-Lightning", "NEBIUS_API_KEY", "cheapest that holds up, with thinking on"),
    "nemotron-nano": (NEBIUS, "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", "NEBIUS_API_KEY", "small and cheap"),
    "deepseek-v4-flash": (NEBIUS, "deepseek-ai/DeepSeek-V4-Flash-0731", "NEBIUS_API_KEY", "tool-heavy agents (14 of 14 tool tasks)"),
    "beam": (NEBIUS, "reflection/beam", "NEBIUS_API_KEY", "multi-hop research at low cost"),
    "qwen3-30b": (NEBIUS, "Qwen/Qwen3-30B-A3B-Instruct-2507", "NEBIUS_API_KEY", "single facts only"),
    "gpt-oss-120b": (NEBIUS, "openai/gpt-oss-120b", "NEBIUS_API_KEY", "general"),
    # local, on your own machine
    "ollama:qwen3": ("http://localhost:11434/v1", "qwen3:4b", "", "local via Ollama (ollama pull qwen3:4b)"),
    "ollama:gpt-oss": ("http://localhost:11434/v1", "gpt-oss:20b", "", "local via Ollama (ollama pull gpt-oss:20b)"),
    "lmstudio": ("http://localhost:1234/v1", os.environ.get("SEARCHIFY_LLM_MODEL", "local-model"), "", "local via LM Studio"),
    "llamacpp:nemotron-nano-9b": ("http://localhost:8081/v1", "nemotron-nano-9b", "", "local via llama.cpp: bartowski/nvidia_NVIDIA-Nemotron-Nano-9B-v2-GGUF"),
}


def resolve(preset: str = "", base_url: str = "", model: str = "") -> Dict:
    """A preset name, or an explicit --base-url/--model for any other OpenAI-compatible server."""
    if preset:
        if preset not in PRESETS:
            raise SystemExit(f"unknown preset {preset!r}; choose from: {', '.join(PRESETS)}")
        url, mid, key_env, _ = PRESETS[preset]
        key = os.environ.get(key_env, "") if key_env else "local"
        if key_env and not key:
            raise SystemExit(f"preset {preset!r} runs on Nebius Token Factory: set {key_env} first")
        return {"base_url": base_url or url, "model": model or mid, "api_key": key}
    return {"base_url": base_url or default_base_url(), "model": model or os.environ.get("SEARCHIFY_LLM_MODEL", "qwen3:4b"),
            "api_key": os.environ.get("SEARCHIFY_LLM_API_KEY", "local")}


def chat(target: Dict) -> None:
    """A chatbot in the terminal: each question runs the tool loop; type 'exit' to stop."""
    print(f"Searchify chat · {target['model']} at {target['base_url']} · "
          f"{'Searchify + Tavily' if complement.has_tavily() else 'Searchify'} · type exit to stop")
    while True:
        try:
            q = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in ("exit", "quit", ""):
            break
        out = ask(q, target["base_url"], target["model"], target["api_key"], log=lambda s: print(f"  · {s}"))
        print(f"\n{out['answer']}\n  ({len(out['tool_calls'])} tool calls, {out['seconds']} s)")
