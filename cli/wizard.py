#!/usr/bin/env python3
"""AI4TAI wizard — настройка .env при первой установке.

Спрашивает ключ Yandex AI Studio, folder id, модель и (необязательно)
токен API technoavia.ru, записывает .env в корень репозитория.
Только стандартная библиотека.

Неинтерактивный режим (CI, скрипты): переменные окружения
YANDEX_CLOUD_API_KEY и YANDEX_CLOUD_FOLDER заданы → .env пишется без
вопросов.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

REPO = Path(__file__).resolve().parent.parent
ENV_FILE = REPO / ".env"

GREEN, YELLOW, BOLD, RESET = "\033[0;32m", "\033[0;33m", "\033[1m", "\033[0m"
DEFAULT_MODEL = "qwen3.6-35b-a3b/latest"

MODELS = [
    ("qwen3.6-35b-a3b/latest", "Qwen 3.6 35B A3B — быстрая, модель курса. Рекомендуется."),
    ("qwen3-235b-a22b-fp8/latest", "Qwen 3 235B — точнее, медленнее и дороже."),
    ("deepseek-v4-flash/latest", "DeepSeek V4 Flash — альтернатива для сравнения."),
]


def banner() -> None:
    print(f"""
  ─── AI4TAI wizard ───────────────────────────────────────────
    Настройка .env: Yandex AI Studio и API сайта technoavia.ru
  ─────────────────────────────────────────────────────────────
""")


def ask(label: str, default: str | None = None, secret: bool = False) -> str:
    hint = f" [{default}]" if default and not secret else ""
    prompt = f"  {label}{hint}: "
    try:
        if secret:
            import getpass
            val = getpass.getpass(prompt)
        else:
            val = input(prompt)
    except (EOFError, KeyboardInterrupt):
        print("\nОтменено.")
        sys.exit(1)
    val = val.strip()
    return default if (not val and default is not None) else val


def ask_choice(label: str, options: list[tuple[str, str]], default: int = 0) -> str:
    print(f"\n  {BOLD}{label}{RESET}")
    for i, (key, desc) in enumerate(options, 1):
        marker = " (по умолчанию)" if i - 1 == default else ""
        print(f"    [{i}] {key}{marker}\n        {desc}")
    while True:
        raw = ask("Номер", default=str(default + 1))
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx][0]
        except ValueError:
            pass
        print(f"  {YELLOW}Введи число от 1 до {len(options)}.{RESET}")


def write_env(api_key: str, folder: str, model: str, taru_api: str = "", taru_user: str = "") -> None:
    lines = [
        "# AI4TAI .env — сгенерировано cli/wizard.py. Не коммитить.",
        "",
        "# === Yandex AI Studio ===",
        f"YANDEX_CLOUD_API_KEY={api_key}",
        f"YANDEX_CLOUD_FOLDER={folder}",
        f"YANDEX_CLOUD_MODEL={model}",
        "",
        "# === Сайт technoavia.ru (необязательно; без токена — локальная копия каталога) ===",
        f'TARU_API="{taru_api}"' if taru_api else "# TARU_API=",
        f"TARU_USER_ID={taru_user}" if taru_user else "# TARU_USER_ID=",
        "# TARU_BASE_URL=https://technoavia.ru/api",
        "# AI4TAI_SITE_MODE=auto",
        "",
        "# === Необязательные настройки ===",
        "# BRAVE_API_KEY=            # поиск через Brave вместо DuckDuckGo",
        "# AI4TAI_EMBEDDER=yandex    # yandex | hash (без сети)",
        "# GOOSE_CONTEXT_LIMIT=128000",
        "",
    ]
    ENV_FILE.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    env_key = os.environ.get("YANDEX_CLOUD_API_KEY", "")
    env_folder = os.environ.get("YANDEX_CLOUD_FOLDER", "")
    non_interactive = bool(env_key and env_folder) and (os.environ.get("AI4TAI_WIZARD_NONINTERACTIVE") == "1"
                                                         or not sys.stdin.isatty())
    if non_interactive:
        write_env(env_key, env_folder, os.environ.get("YANDEX_CLOUD_MODEL", DEFAULT_MODEL),
                  os.environ.get("TARU_API", ""), os.environ.get("TARU_USER_ID", ""))
        print(f"[ok] .env записан из переменных окружения: {ENV_FILE}")
        return 0

    banner()
    if ENV_FILE.exists():
        print(f"  {YELLOW}[warn]{RESET} {ENV_FILE} уже существует.")
        if ask("Перезаписать? (y/N)", default="N").lower() not in ("y", "yes", "д", "да"):
            print("  Оставляю существующий .env без изменений.")
            return 0

    print("  Ключ и folder id Yandex AI Studio выдаются на курсе.")
    print("  Самостоятельно: https://yandex.cloud/ru/docs/ai-studio/quickstart")
    print()
    api_key = ask("YANDEX_CLOUD_API_KEY", secret=True)
    if len(api_key) < 20:
        print(f"  {YELLOW}Ключ выглядит коротким. Продолжаю; doctor это покажет.{RESET}")
    folder = ask("YANDEX_CLOUD_FOLDER (вида b1g...)")
    model = ask_choice("Модель по умолчанию", MODELS, default=0)
    print()
    print("  Токен API сайта technoavia.ru — необязательно. Без него агент")
    print("  работает с локальной копией каталога (data/catalog_mock.json).")
    taru_api = ask("TARU_API (Enter — пропустить)", default="")
    taru_user = ask("TARU_USER_ID (Enter — пропустить)", default="") if taru_api else ""
    write_env(api_key, folder, model, taru_api, taru_user)
    print()
    print(f"  {GREEN}[ok]{RESET} .env записан: {ENV_FILE}")
    print(f"  Модель: {BOLD}{model}{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
