"""Шаблон собственного MCP-сервера. День 3, практика 3.

Запуск для проверки (сервер ждёт JSON-RPC на stdin, это нормально):

    .venv\\Scripts\\python.exe templates\\mcp\\s01_hello.py

Подключение к агенту: скопировать файл в свой проект, добавить в
recipes/ai4tai.yaml второй блок extensions (см. templates/mcp/README.md).

Правила:
  * функция с типизированными аргументами и docstring — это всё, что
    видит модель; docstring пишется для модели;
  * возвращать строку; ошибки возвращать текстом «ERROR: ...», а не
    исключением;
  * побочные эффекты (запись, удаление, сетевые вызовы) — только явно
    описанные в docstring.
"""
from __future__ import annotations

import platform
import socket
import subprocess
import sys
from datetime import datetime

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-tools")


@mcp.tool()
def hello(name: str = "мир") -> str:
    """Проверочный инструмент. Возвращает приветствие и текущее время."""
    return f"Привет, {name}. Сейчас {datetime.now():%Y-%m-%d %H:%M:%S}."


@mcp.tool()
def host_info() -> str:
    """Имя компьютера, ОС и версия Python, на которых запущен MCP-сервер."""
    return (
        f"host: {socket.gethostname()}\n"
        f"os: {platform.platform()}\n"
        f"python: {sys.version.split()[0]}"
    )


@mcp.tool()
def ping_host(host: str, count: int = 2) -> str:
    """Проверить доступность узла командой ping. Возвращает вывод команды.
    Только чтение сети, ничего не меняет."""
    flag = "-n" if sys.platform == "win32" else "-c"
    try:
        out = subprocess.run(
            ["ping", flag, str(max(1, min(int(count), 5))), host],
            capture_output=True, text=True, timeout=20,
        )
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"
    return (out.stdout or out.stderr).strip()[:2000]


# Место для своего инструмента. Примеры для проектов:
#   - чтение журнала событий Windows: Get-WinEvent через subprocess
#   - запрос к 1С OData: requests.get(f"{ODATA_BASE}/Catalog_Номенклатура", auth=...)
#   - проверка ссылки на сайте: requests.head(url).status_code


if __name__ == "__main__":
    mcp.run()
