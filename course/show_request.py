#!/usr/bin/env python3
"""Показать, что реально уходит в модель: разбор последнего запроса из логов Goose.

Демо дня 1 («вот ядро, вот промпты»). Ищет самый свежий файл
llm_request.*.jsonl в стандартных папках Goose и печатает:
системный промпт (начало), список инструментов со схемами, сообщения
диалога с вызовами инструментов.

    python show_request.py            # последний запрос последнего файла
    python show_request.py --all      # все запросы файла кратко
    python show_request.py --tools    # полные схемы инструментов
    python show_request.py --file <путь к jsonl>
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass


def candidate_dirs() -> list[Path]:
    home = Path.home()
    dirs = [
        home / ".local" / "state" / "goose" / "logs",
        home / ".local" / "share" / "goose" / "logs",
    ]
    for env in ("LOCALAPPDATA", "APPDATA"):
        base = os.environ.get(env)
        if base:
            dirs += [Path(base) / "Block" / "goose" / "logs",
                     Path(base) / "Block" / "goose" / "data" / "logs",
                     Path(base) / "goose" / "logs"]
    if os.environ.get("XDG_STATE_HOME"):
        dirs.append(Path(os.environ["XDG_STATE_HOME"]) / "goose" / "logs")
    return dirs


def has_messages(path: Path) -> bool:
    try:
        return any(request_body(e).get("messages") for e in load_requests(path))
    except Exception:
        return False


def find_latest() -> Path | None:
    files: list[Path] = []
    for d in candidate_dirs():
        if d.exists():
            files += [Path(p) for p in glob.glob(str(d / "**" / "llm_request*.jsonl"), recursive=True)]
    if not files and os.environ.get("LOCALAPPDATA"):
        root = Path(os.environ["LOCALAPPDATA"]) / "Block"
        if root.exists():
            files += [Path(p) for p in glob.glob(str(root / "**" / "llm_request*.jsonl"), recursive=True)]
    files = [f for f in files if f.exists()]
    for f in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True):
        if has_messages(f):
            return f
    return None


def load_requests(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def request_body(entry: dict) -> dict:
    for k in ("input", "request", "payload", "body"):
        if isinstance(entry.get(k), dict) and "messages" in entry[k]:
            return entry[k]
    for v in entry.values():
        if isinstance(v, dict) and "messages" in v:
            return v
    return entry


def short(s: str, n: int) -> str:
    s = s.replace("\n", "\n    ")
    return s if len(s) <= n else s[:n] + " …"


def describe(req: dict, full_tools: bool = False) -> None:
    print(f"model:       {req.get('model')}")
    print(f"temperature: {req.get('temperature')}   max_tokens: {req.get('max_tokens')}")
    msgs = req.get("messages", [])
    tools = req.get("tools", [])
    print(f"messages:    {len(msgs)}   tools: {len(tools)}")
    print()

    print("=== 1. СИСТЕМНЫЙ ПРОМПТ (messages[0]) — из recipes/ai4tai.yaml ===")
    if msgs and msgs[0].get("role") == "system":
        c = msgs[0]["content"]
        c = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
        print(f"    длина: {len(c)} символов")
        print("    " + short(c, 900))
    print()

    print("=== 2. ИНСТРУМЕНТЫ (tools) — схемы из docstring и типов аргументов ===")
    for t in tools:
        fn = t.get("function", t)
        name = fn.get("name")
        desc = (fn.get("description") or "").strip().splitlines()[0] if fn.get("description") else ""
        params = list((fn.get("parameters") or {}).get("properties", {}).keys())
        print(f"    {name:32s} ({', '.join(params)})  — {desc[:70]}")
    if full_tools and tools:
        print()
        print(json.dumps(tools, ensure_ascii=False, indent=2)[:6000])
    print()

    print("=== 3. ДИАЛОГ (messages[1:]) — включая вызовы инструментов и их результаты ===")
    for i, m in enumerate(msgs[1:], 1):
        role = m.get("role")
        c = m.get("content")
        tc = m.get("tool_calls")
        if tc:
            for call in tc:
                fn = call.get("function", {})
                print(f"  [{i}] {role}: ВЫЗОВ {fn.get('name')}({short(str(fn.get('arguments')), 200)})")
        if c:
            s = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
            print(f"  [{i}] {role}: {short(s, 400)}")
        if m.get("tool_call_id"):
            pass
    print()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--tools", action="store_true")
    a = ap.parse_args()
    path = Path(a.file) if a.file else find_latest()
    if not path or not path.exists():
        print("Лог не найден. Папки, где искали:")
        for d in candidate_dirs():
            print("  ", d)
        return 1
    print(f"файл: {path}")
    entries = load_requests(path)
    print(f"запросов к модели в файле: {len(entries)}\n")
    if a.all:
        for k, e in enumerate(entries, 1):
            req = request_body(e)
            msgs = req.get("messages", [])
            last = msgs[-1] if msgs else {}
            print(f"#{k}: messages={len(msgs)} tools={len(req.get('tools', []))} last_role={last.get('role')}")
        return 0
    entries = [e for e in entries if request_body(e).get("messages")]
    if not entries:
        print("в файле нет запросов с сообщениями")
        return 1
    describe(request_body(entries[-1]), full_tools=a.tools)
    return 0


if __name__ == "__main__":
    sys.exit(main())
