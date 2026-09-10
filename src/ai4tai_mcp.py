"""AI4TAI MCP server — один stdio-процесс со всеми инструментами агента.

Инструменты (namespace Goose: `ai4tai`):

  Служебные
    token_budget()                     расход токенов за сегодня
    load_artifact(id)                  полный текст усечённого результата
    list_skills() / load_skill(name)   модульные инструкции (skills/*.md)

  Сайт technoavia.ru
    site_status()                      режим (live/mock), доступность API
    site_search(query, limit)          поиск товаров
    site_product(sku)                  карточка товара
    site_categories()                  дерево категорий

  База данных (SQLite, учебная база «номенклатура / остатки / заказы»)
    sqlite_schema(db_path)             таблицы, колонки, число строк
    sqlite_query(sql, db_path, max_rows) SELECT-запрос (запись только при AI4TAI_DB_WRITE=1)

  RAG по документам
    rag_status(index_path)             состояние индекса
    rag_search(query, top_k, index_path) поиск фрагментов с указанием источника

  Веб
    web_search(query, n)               Brave (при ключе) или DuckDuckGo
    web_fetch(url, max_chars)          GET + HTML→text

  PDF
    pdf_info / pdf_read / pdf_search   чтение локальных PDF

Переменные окружения (все необязательны):

  TARU_BASE_URL        https://technoavia.ru/api   базовый URL API сайта
  TARU_API             токен API сайта (Bearer)
  AI4TAI_SITE_MODE     auto | live | mock          (auto: live, при сбое mock)
  AI4TAI_CATALOG_MOCK  src/fixtures/catalog_mock.json  локальная копия каталога
  AI4TAI_DB_PATH       .data/demo.sqlite               учебная база
  AI4TAI_DB_WRITE=1    разрешить запись в базу
  AI4TAI_RAG_DB        .rag/index.sqlite           индекс RAG
  AI4TAI_SKILLS_DIR    skills/                     каталог skills
  AI4TAI_WEB_DISABLED=1 отключить web_search / web_fetch
  BRAVE_API_KEY        поиск через Brave вместо DuckDuckGo
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Force UTF-8 for stdio JSON-RPC on Windows — MCP protocol is UTF-8 native.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stdin.reconfigure(encoding="utf-8")   # type: ignore[attr-defined]
    except Exception:
        pass

import requests
from mcp.server.fastmcp import FastMCP
from pypdf import PdfReader

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import rag_index  # noqa: E402
import demo_db  # noqa: E402

mcp = FastMCP("ai4tai")

# ---------- config ----------

TARU_BASE_URL = os.environ.get("TARU_BASE_URL", "https://technoavia.ru/api").rstrip("/")
TARU_API = os.environ.get("TARU_API", "")
SITE_MODE = os.environ.get("AI4TAI_SITE_MODE", "auto").lower()
CATALOG_MOCK = Path(os.environ.get("AI4TAI_CATALOG_MOCK", HERE / "fixtures" / "catalog_mock.json"))
DB_PATH = Path(os.environ.get("AI4TAI_DB_PATH", REPO / ".data" / "demo.sqlite"))
DB_WRITE = os.environ.get("AI4TAI_DB_WRITE") == "1"
RAG_DB = Path(os.environ.get("AI4TAI_RAG_DB", REPO / ".rag" / "index.sqlite"))
WEB_DISABLED = os.environ.get("AI4TAI_WEB_DISABLED") == "1"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI4TAI/1.0"
MAX_RESULTS = 10
CHARS_PER_HIT = 400
PDF_DEFAULT_MAX_CHARS = 8000
WEB_DEFAULT_MAX_CHARS = 3000
SITE_TIMEOUT = (5, 15)


def _fmt_err(tool: str, e: Exception) -> str:
    return f"ERROR [{tool}]: {type(e).__name__}: {str(e)[:300]}"


def _truncate(s: str | None, n: int = CHARS_PER_HIT) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 3] + "..."


# ========================================================================
# Artifact cache — усечение тяжёлых результатов
# ========================================================================

_ARTIFACTS: dict[str, dict] = {}
_ARTIFACT_COUNTER = 0
ARTIFACT_THRESHOLD = 800
ARTIFACT_PREVIEW = 500


def _store_artifact(tool: str, content: str) -> str:
    global _ARTIFACT_COUNTER
    _ARTIFACT_COUNTER += 1
    aid = f"{tool}_{_ARTIFACT_COUNTER:04d}"
    _ARTIFACTS[aid] = {"tool": tool, "content": content, "size": len(content)}
    return aid


def _maybe_trim(tool: str, content: str) -> str:
    if len(content) <= ARTIFACT_THRESHOLD:
        return content
    aid = _store_artifact(tool, content)
    preview = content[:ARTIFACT_PREVIEW].rstrip()
    return (
        f"{preview}\n\n"
        f"[... усечено, полный размер {len(content):,} симв. | "
        f"artifact_id: {aid} | для полного текста: load_artifact(\"{aid}\")]"
    )


@mcp.tool()
def token_budget() -> str:
    """Расход токенов за сегодня: использовано / лимит / остаток.

    Читает счётчик, который ведёт token proxy. Вызывать, когда пользователь
    спрашивает о стоимости, перед тяжёлыми операциями и раз в 5–7 вызовов."""
    try:
        path = Path.home() / ".ai4tai_budget.json"
        from datetime import date
        today = date.today().isoformat()
        try:
            d = json.loads(path.read_text())
            used = d.get("tokens", 0) if d.get("date") == today else 0
        except Exception:
            used = 0
        limit = int(os.environ.get("AI4TAI_DAILY_TOKEN_LIMIT", "3000000"))
        remaining = max(0, limit - used)
        pct = (used * 100) // limit if limit else 0
        return (
            f"Токен-бюджет на сегодня: {used:,} / {limit:,} ({pct}%). "
            f"Осталось {remaining:,}. Сброс — в полночь локального времени."
        )
    except Exception as e:
        return f"ERROR [token_budget]: {type(e).__name__}: {e}"


@mcp.tool()
def load_artifact(artifact_id: str) -> str:
    """Полный текст усечённого результата по artifact_id (например "web_search_0003").

    Содержимое живёт в памяти MCP-процесса до конца сессии. Вызывать только
    когда нужен именно полный текст."""
    a = _ARTIFACTS.get(artifact_id)
    if a is None:
        available = sorted(_ARTIFACTS.keys())
        return (
            f"ERROR: artifact '{artifact_id}' не найден. "
            f"Доступно {len(available)}: {', '.join(available[-10:])}"
        )
    return a["content"]


# ========================================================================
# Skills
# ========================================================================

_SKILLS_DIR_ENV = os.environ.get("AI4TAI_SKILLS_DIR")
if _SKILLS_DIR_ENV:
    SKILLS_DIR = Path(_SKILLS_DIR_ENV).expanduser().resolve()
else:
    SKILLS_DIR = (REPO / "skills").resolve()


def _parse_skill_frontmatter(path: Path) -> dict:
    """Frontmatter вида ---\\nname: ...\\ndescription: ...\\n--- без зависимости от yaml."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    out: dict = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip()
    return out


@mcp.tool()
def list_skills() -> str:
    """Список доступных skills с описанием и словами-триггерами."""
    if not SKILLS_DIR.exists():
        return f"ERROR: skills dir не найден: {SKILLS_DIR}"
    items = []
    for p in sorted(SKILLS_DIR.glob("*.md")):
        fm = _parse_skill_frontmatter(p)
        name = fm.get("name") or p.stem
        desc = fm.get("description") or ""
        triggers = fm.get("triggers") or ""
        combines = fm.get("combines_with") or ""
        entry = f"  - {name}\n    description:   {desc}"
        if triggers:
            entry += f"\n    triggers:      {triggers}"
        if combines:
            entry += f"\n    combines with: {combines}"
        items.append(entry)
    if not items:
        return f"{SKILLS_DIR}: (пусто)"
    return (
        f"Доступные skills в {SKILLS_DIR}:\n\n"
        + "\n\n".join(items)
        + "\n\nВызови `load_skill(<name>)`, чтобы прочитать полный текст skill. "
        + "Несколько skills можно загружать последовательно."
    )


@mcp.tool()
def load_skill(name: str) -> str:
    """Загрузить skill по имени (powershell, 1c-query, sqlite, react, python, debug-loop, markdown).
    Вызывать перед написанием кода или документа в соответствующей области."""
    if not SKILLS_DIR.exists():
        return f"ERROR: skills dir не найден: {SKILLS_DIR}"
    safe = Path(name).name.replace(".md", "")
    p = SKILLS_DIR / f"{safe}.md"
    if not p.exists():
        available = sorted(q.stem for q in SKILLS_DIR.glob("*.md"))
        return f"ERROR: skill '{safe}' не найден. Доступные: " + ", ".join(available)
    try:
        content = p.read_text(encoding="utf-8")
    except Exception as e:
        return _fmt_err(f"load_skill({safe})", e)
    return f"# Skill: {safe}\n# File: {p}\n\n{content}"


# ========================================================================
# Сайт technoavia.ru — live API с fallback на локальную копию каталога
# ========================================================================

class SiteUnavailable(Exception):
    """API сайта недоступно или вернуло не JSON (капча, редирект, HTML)."""


_CATALOG_CACHE: list[dict] | None = None


def _mock_catalog() -> list[dict]:
    global _CATALOG_CACHE
    if _CATALOG_CACHE is None:
        with open(CATALOG_MOCK, encoding="utf-8") as f:
            data = json.load(f)
        _CATALOG_CACHE = data["products"] if isinstance(data, dict) else data
    return _CATALOG_CACHE


def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^\wёЁ-]+", (s or "").casefold()) if len(t) > 1]


def _mock_score(product: dict, query: str) -> float:
    q = _tokens(query)
    if not q:
        return 0.0
    name = (product.get("name") or "").casefold()
    desc = (product.get("description") or "").casefold()
    cat = (product.get("category") or "").casefold()
    props = " ".join(
        str(v) for v in (product.get("properties") or {}).values()
    ).casefold()
    sku = (product.get("sku") or "").casefold()
    score = 0.0
    for t in q:
        if t == sku:
            score += 10
        if t in name:
            score += 3
        if t in cat:
            score += 2
        if t in props:
            score += 1.5
        if t in desc:
            score += 1
    return score


def _mock_search(query: str, limit: int) -> list[dict]:
    scored = [(_mock_score(p, query), p) for p in _mock_catalog()]
    scored = [x for x in scored if x[0] > 0]
    scored.sort(key=lambda x: (-x[0], x[1].get("sku", "")))
    return [p for _, p in scored[:limit]]


def _mock_product(sku: str) -> dict | None:
    s = (sku or "").strip().casefold()
    for p in _mock_catalog():
        if (p.get("sku") or "").casefold() == s:
            return p
    return None


def _site_headers() -> dict:
    h = {"Accept": "application/json", "User-Agent": UA}
    if TARU_API:
        h["Authorization"] = f"Bearer {TARU_API}"
    return h


def _site_live_get(path: str, params: dict | None = None) -> dict | list:
    """GET к API сайта. Любой не-JSON ответ (капча, HTML) → SiteUnavailable."""
    url = f"{TARU_BASE_URL}/{path.lstrip('/')}"
    try:
        r = requests.get(url, params=params, headers=_site_headers(), timeout=SITE_TIMEOUT)
    except Exception as e:
        raise SiteUnavailable(f"{type(e).__name__}: {str(e)[:150]}") from e
    ct = r.headers.get("Content-Type", "")
    if r.status_code >= 400:
        raise SiteUnavailable(f"HTTP {r.status_code}")
    if "json" not in ct.lower():
        kind = "капча" if "captcha" in r.text[:3000].lower() or "не робот" in r.text[:3000].lower() else "HTML"
        raise SiteUnavailable(f"ответ не JSON ({kind}, Content-Type: {(ct or '?').split(';')[0]})")
    try:
        return r.json()
    except ValueError as e:
        raise SiteUnavailable("тело ответа не разбирается как JSON") from e


def _fmt_product_short(p: dict) -> str:
    price = p.get("price")
    price_s = f"{price:,.0f} ₽".replace(",", " ") if isinstance(price, (int, float)) else str(price or "—")
    return (
        f"  • {p.get('sku')}  {p.get('name')}\n"
        f"    категория: {p.get('category', '—')} | цена: {price_s} / {p.get('unit', 'шт')}\n"
        f"    {_truncate(p.get('description'), 160)}"
    )


def _fmt_product_full(p: dict) -> str:
    lines = [
        f"Артикул: {p.get('sku')}",
        f"Название: {p.get('name')}",
        f"Категория: {p.get('category', '—')}",
        f"Цена: {p.get('price', '—')} ₽ / {p.get('unit', 'шт')}",
    ]
    props = p.get("properties") or {}
    if props:
        lines.append("Свойства:")
        for k, v in props.items():
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v)
            lines.append(f"  - {k}: {v}")
    if p.get("description"):
        lines.append(f"Описание: {p['description']}")
    if p.get("url"):
        lines.append(f"Ссылка: {p['url']}")
    return "\n".join(lines)


def _normalize_live_product(item: dict) -> dict:
    """Привести ответ живого API к полям локального каталога (по возможности)."""
    return {
        "sku": item.get("clear_sku") or item.get("sku") or item.get("article") or item.get("id"),
        "name": item.get("name") or item.get("title"),
        "category": (item.get("category") or {}).get("name") if isinstance(item.get("category"), dict)
                    else item.get("category"),
        "price": item.get("price"),
        "unit": item.get("unit", "шт"),
        "properties": item.get("properties") or {},
        "description": item.get("description") or item.get("short_description") or "",
        "url": item.get("url"),
        "_raw": item,
    }


def _site_try_live(fn, mock_fn, tool: str):
    """Выбор источника по AI4TAI_SITE_MODE.

    live  — только API; при сбое возвращается ERROR.
    mock  — только локальная копия.
    auto  — API, при сбое локальная копия с пометкой."""
    if SITE_MODE == "mock":
        return mock_fn(), "mock"
    if SITE_MODE == "auto" and not TARU_API:
        return mock_fn(), "mock (токен TARU_API не задан)"
    try:
        return fn(), "live"
    except SiteUnavailable as e:
        if SITE_MODE == "live":
            raise
        return mock_fn(), f"mock (API недоступно: {e})"


@mcp.tool()
def site_status() -> str:
    """Режим доступа к сайту technoavia.ru (live / mock), наличие токена, доступность API."""
    lines = [
        f"Режим: {SITE_MODE}",
        f"Base URL: {TARU_BASE_URL}",
        f"Токен TARU_API: {'задан' if TARU_API else 'не задан'}",
        f"Локальная копия каталога: {CATALOG_MOCK} "
        f"({len(_mock_catalog()) if CATALOG_MOCK.exists() else 'файл не найден'} позиций)",
    ]
    if SITE_MODE == "mock":
        lines.append("API: не используется (режим mock)")
    elif SITE_MODE == "auto" and not TARU_API:
        lines.append("API: не используется (нет токена, работает локальная копия)")
    else:
        try:
            _site_live_get("categories")
            lines.append("API: отвечает JSON")
        except SiteUnavailable as e:
            lines.append(f"API: недоступно ({e}); в режиме auto используется локальная копия")
    return "\n".join(lines)


@mcp.tool()
def site_search(query: str, limit: int = 5) -> str:
    """Поиск товаров на technoavia.ru по названию, категории, свойству или артикулу.
    Возвращает артикул, название, категорию, цену и краткое описание."""
    n = max(1, min(int(limit), MAX_RESULTS))

    def live():
        data = _site_live_get("search", {"q": query, "limit": n})
        items = data.get("data") if isinstance(data, dict) else data
        return [_normalize_live_product(x) for x in (items or [])[:n]]

    try:
        products, source = _site_try_live(live, lambda: _mock_search(query, n), "site_search")
    except SiteUnavailable as e:
        return f"ERROR [site_search]: API недоступно: {e}"
    except Exception as e:
        return _fmt_err("site_search", e)
    if not products:
        return f"Ничего не найдено по запросу «{query}» (источник: {source})."
    out = [f"Найдено {len(products)} по «{query}» (источник: {source}):"]
    out += [_fmt_product_short(p) for p in products]
    return _maybe_trim("site_search", "\n".join(out))


@mcp.tool()
def site_product(sku: str) -> str:
    """Карточка товара technoavia.ru по артикулу: свойства, описание, цена, ссылка."""

    def live():
        data = _site_live_get(f"products/{sku}")
        item = data.get("data") if isinstance(data, dict) and "data" in data else data
        return _normalize_live_product(item) if item else None

    try:
        product, source = _site_try_live(live, lambda: _mock_product(sku), "site_product")
    except SiteUnavailable as e:
        return f"ERROR [site_product]: API недоступно: {e}"
    except Exception as e:
        return _fmt_err("site_product", e)
    if not product:
        return f"Товар с артикулом «{sku}» не найден (источник: {source})."
    return _maybe_trim("site_product", f"(источник: {source})\n{_fmt_product_full(product)}")


@mcp.tool()
def site_categories() -> str:
    """Список категорий каталога technoavia.ru с числом позиций."""

    def live():
        data = _site_live_get("categories")
        items = data.get("data") if isinstance(data, dict) else data
        return [(c.get("name"), c.get("products_count")) for c in (items or [])]

    def mock():
        counts: dict[str, int] = {}
        for p in _mock_catalog():
            counts[p.get("category", "—")] = counts.get(p.get("category", "—"), 0) + 1
        return sorted(counts.items())

    try:
        cats, source = _site_try_live(live, mock, "site_categories")
    except SiteUnavailable as e:
        return f"ERROR [site_categories]: API недоступно: {e}"
    except Exception as e:
        return _fmt_err("site_categories", e)
    lines = [f"Категории (источник: {source}):"]
    for name, cnt in cats:
        lines.append(f"  - {name}" + (f" ({cnt})" if cnt is not None else ""))
    return _maybe_trim("site_categories", "\n".join(lines))


# ========================================================================
# SQLite — учебная база «номенклатура / остатки / заказы»
# ========================================================================

_READ_ONLY_PREFIXES = ("select", "with", "pragma", "explain")


def _resolve_db(db_path: str) -> Path:
    p = Path(db_path).expanduser() if db_path else DB_PATH
    if not p.is_absolute():
        p = Path.cwd() / p
    if p == DB_PATH.resolve() or p == DB_PATH:
        if not p.exists():
            demo_db.build(p)
    return p


def _connect(p: Path, write: bool) -> sqlite3.Connection:
    if write:
        return sqlite3.connect(str(p))
    return sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)


def _fmt_table(cols: list[str], rows: list[tuple]) -> str:
    def cell(v) -> str:
        if v is None:
            return "NULL"
        if isinstance(v, float):
            return f"{v:g}"
        return str(v).replace("\n", " ")
    srows = [[cell(v) for v in r] for r in rows]
    widths = [len(c) for c in cols]
    for r in srows:
        for i, v in enumerate(r):
            widths[i] = max(widths[i], min(len(v), 40))
    def line(vals):
        return " | ".join(v[:40].ljust(widths[i]) for i, v in enumerate(vals))
    out = [line(cols), "-+-".join("-" * w for w in widths)]
    out += [line(r) for r in srows]
    return "\n".join(out)


@mcp.tool()
def sqlite_schema(db_path: str = "") -> str:
    """Схема SQLite-базы: таблицы, колонки, число строк. По умолчанию — учебная база .data/demo.sqlite."""
    try:
        p = _resolve_db(db_path)
        if not p.exists():
            return f"ERROR: база не найдена: {p}"
        con = _connect(p, write=False)
        try:
            tables = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )]
            lines = [f"База: {p}", f"Таблиц: {len(tables)}"]
            for t in tables:
                cols = con.execute(f'PRAGMA table_info("{t}")').fetchall()
                n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                col_s = ", ".join(f"{c[1]} {c[2]}{' PK' if c[5] else ''}" for c in cols)
                lines.append(f"\n{t} ({n} строк)\n  {col_s}")
        finally:
            con.close()
        return _maybe_trim("sqlite_schema", "\n".join(lines))
    except Exception as e:
        return _fmt_err("sqlite_schema", e)


@mcp.tool()
def sqlite_query(sql: str, db_path: str = "", max_rows: int = 50) -> str:
    """Выполнить SQL к SQLite-базе и вернуть таблицу результата.
    Разрешены только SELECT / WITH / PRAGMA / EXPLAIN; запись — при AI4TAI_DB_WRITE=1.
    Перед запросом посмотри схему через sqlite_schema."""
    try:
        p = _resolve_db(db_path)
        if not p.exists():
            return f"ERROR: база не найдена: {p}"
        stmt = sql.strip().rstrip(";").strip()
        first = (stmt.split(None, 1)[0] if stmt else "").casefold()
        is_read = first in _READ_ONLY_PREFIXES
        if not is_read and not DB_WRITE:
            return (
                f"ERROR: запрос «{first.upper()}» изменяет базу. Разрешены SELECT/WITH/PRAGMA/EXPLAIN. "
                "Для записи запусти агента с AI4TAI_DB_WRITE=1."
            )
        con = _connect(p, write=not is_read)
        try:
            cur = con.execute(stmt)
            if cur.description is None:
                con.commit()
                return f"OK: выполнено, изменено строк: {cur.rowcount}"
            cols = [d[0] for d in cur.description]
            limit = max(1, min(int(max_rows), 500))
            rows = cur.fetchmany(limit + 1)
        finally:
            con.close()
        more = len(rows) > limit
        rows = rows[:limit]
        out = _fmt_table(cols, rows)
        tail = f"\n\n{len(rows)} строк" + (f" (показаны первые {limit}, есть ещё)" if more else "")
        return _maybe_trim("sqlite_query", out + tail)
    except sqlite3.Error as e:
        return f"ERROR [sqlite_query]: {e}"
    except Exception as e:
        return _fmt_err("sqlite_query", e)


# ========================================================================
# RAG по документам
# ========================================================================

def _resolve_index(index_path: str) -> Path:
    p = Path(index_path).expanduser() if index_path else RAG_DB
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


@mcp.tool()
def rag_status(index_path: str = "") -> str:
    """Состояние RAG-индекса: путь, число документов и фрагментов, модель эмбеддингов."""
    p = _resolve_index(index_path)
    if not p.exists():
        return (
            f"Индекс не найден: {p}\n"
            f"Создать: python src/rag_index.py index <папка с документами> --db {p}"
        )
    try:
        st = rag_index.index_stats(p)
    except Exception as e:
        return _fmt_err("rag_status", e)
    return (
        f"Индекс: {p}\nДокументов: {st['docs']}\nФрагментов: {st['chunks']}\n"
        f"Эмбеддер: {st['embedder']} (dim={st['dim']})\nСоздан: {st['created']}"
    )


@mcp.tool()
def rag_search(query: str, top_k: int = 5, index_path: str = "") -> str:
    """Поиск по локальному RAG-индексу документов. Возвращает фрагменты с именем файла,
    строками и оценкой близости. Ответ пользователю формулируй с указанием источника."""
    p = _resolve_index(index_path)
    if not p.exists():
        return (
            f"ERROR: индекс не найден: {p}. "
            f"Создай: python src/rag_index.py index <папка> --db {p}"
        )
    try:
        hits = rag_index.search(p, query, top_k=max(1, min(int(top_k), 20)))
    except Exception as e:
        return _fmt_err("rag_search", e)
    if not hits:
        return f"По запросу «{query}» ничего не найдено в {p}."
    lines = [f"Найдено {len(hits)} фрагментов по «{query}»:"]
    for h in hits:
        lines.append(
            f"\n[{h['score']:.3f}] {h['path']} (строки {h['start_line']}–{h['end_line']})\n"
            f"{_truncate(h['text'], 600)}"
        )
    return _maybe_trim("rag_search", "\n".join(lines))


# ========================================================================
# Web search / fetch
# ========================================================================

def _strip_html(html: str) -> str:
    html = re.sub(r"<(script|style|noscript)[\s\S]*?</\1>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _ddg_search(query: str, num: int) -> list[dict]:
    r = requests.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query},
        headers={"User-Agent": UA},
        timeout=20,
    )
    r.raise_for_status()
    html = r.text
    results = []
    for m in re.finditer(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
        r'.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        html,
        flags=re.DOTALL,
    ):
        url, title, snippet = m.group(1), _strip_html(m.group(2)), _strip_html(m.group(3))
        if url.startswith("//duckduckgo.com/l/?uddg="):
            q = parse_qs(urlparse("https:" + url).query)
            url = q.get("uddg", [url])[0]
        results.append({"url": url, "title": title, "snippet": snippet[:400]})
        if len(results) >= num:
            break
    return results


def _brave_search(query: str, num: int, api_key: str) -> list[dict]:
    r = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": num},
        headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    out = []
    for w in (data.get("web") or {}).get("results", [])[:num]:
        out.append({"url": w.get("url"), "title": w.get("title"), "snippet": w.get("description", "")[:400]})
    return out


@mcp.tool()
def web_search(query: str, num_results: int = 5) -> str:
    """Поиск в интернете (Brave при наличии ключа, иначе DuckDuckGo). Возвращает заголовок, URL, фрагмент."""
    if WEB_DISABLED:
        return "ERROR: web_search отключён через AI4TAI_WEB_DISABLED."
    key = os.environ.get("BRAVE_API_KEY")
    n = min(max(num_results, 1), MAX_RESULTS)
    try:
        results = _brave_search(query, n, key) if key else _ddg_search(query, n)
    except Exception as e:
        return _fmt_err("web_search", e)
    if not results:
        return f"Ничего не найдено по запросу «{query}»."
    lines = [f"Результаты по «{query}» (провайдер: {'brave' if key else 'duckduckgo'}):"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}")
    return _maybe_trim("web_search", "\n".join(lines))


@mcp.tool()
def web_fetch(url: str, max_chars: int = WEB_DEFAULT_MAX_CHARS) -> str:
    """Загрузить страницу по URL, убрать HTML, вернуть текст. Для PDF — скачать через shell и читать pdf_read."""
    if WEB_DISABLED:
        return "ERROR: web_fetch отключён через AI4TAI_WEB_DISABLED."
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        r.raise_for_status()
    except Exception as e:
        return _fmt_err("web_fetch", e)
    ct = r.headers.get("Content-Type", "")
    body = r.text
    if "html" in ct.lower():
        body = _strip_html(body)
    if len(body) > max_chars:
        body = body[:max_chars] + f"\n\n[... truncated, total {len(r.text)} chars ...]"
    return _maybe_trim("web_fetch", f"{url}\nContent-Type: {ct}\n\n{body}")


# ========================================================================
# PDF
# ========================================================================

def _pdf_resolve(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


def _pdf_parse_pages(spec: str, total: int) -> list[int]:
    pages: set[int] = set()
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
            for i in range(start, end + 1):
                if 1 <= i <= total:
                    pages.add(i - 1)
        else:
            i = int(part)
            if 1 <= i <= total:
                pages.add(i - 1)
    return sorted(pages)


def _pdf_suggest_near(p: Path) -> str:
    parent = p.parent if p.parent.exists() else Path.cwd()
    try:
        candidates = sorted(parent.glob("*.pdf"))
    except Exception:
        candidates = []
    if not candidates:
        return ""
    listing = "\n".join(f"  - {c}" for c in candidates[:10])
    return f"\nДоступные PDF в {parent}:\n{listing}"


@mcp.tool()
def pdf_info(path: str) -> str:
    """Число страниц, метаданные и размер локального PDF."""
    p = _pdf_resolve(path)
    if not p.exists():
        return f"ERROR: файл не найден: {p}{_pdf_suggest_near(p)}"
    try:
        reader = PdfReader(str(p))
    except Exception as e:
        return _fmt_err("pdf_info", e)
    n = len(reader.pages)
    meta = reader.metadata or {}
    size = p.stat().st_size
    lines = [f"PDF: {p}", f"Страниц: {n}", f"Размер: {size} байт"]
    for k in ("/Title", "/Author", "/Subject", "/Creator", "/Producer"):
        if meta.get(k):
            lines.append(f"{k[1:]}: {meta[k]}")
    return "\n".join(lines)


@mcp.tool()
def pdf_read(path: str, pages: str = "1-5", max_chars: int = PDF_DEFAULT_MAX_CHARS) -> str:
    """Текст со страниц PDF. pages: "1-3" или "1,3,5". По умолчанию первые 5."""
    p = _pdf_resolve(path)
    if not p.exists():
        return f"ERROR: файл не найден: {p}{_pdf_suggest_near(p)}"
    try:
        reader = PdfReader(str(p))
    except Exception as e:
        return _fmt_err("pdf_read", e)
    total = len(reader.pages)
    idxs = _pdf_parse_pages(pages, total)
    if not idxs:
        return f"ERROR: пустой или некорректный диапазон «{pages}» (всего {total})"
    parts = []
    for i in idxs:
        try:
            txt = reader.pages[i].extract_text() or ""
        except Exception as e:
            txt = f"[error on page {i + 1}: {e}]"
        parts.append(f"\n=== стр. {i + 1} ===\n{txt.strip()}")
    out = "\n".join(parts).strip()
    if len(out) > max_chars:
        out = out[:max_chars] + f"\n\n[... truncated, {len(out) - max_chars} chars cut ...]"
    return _maybe_trim("pdf_read", out)


@mcp.tool()
def pdf_search(path: str, query: str, context: int = 120) -> str:
    """Поиск подстроки в PDF. Возвращает номер страницы и контекст."""
    p = _pdf_resolve(path)
    if not p.exists():
        return f"ERROR: файл не найден: {p}{_pdf_suggest_near(p)}"
    try:
        reader = PdfReader(str(p))
    except Exception as e:
        return _fmt_err("pdf_search", e)
    import unicodedata

    def norm(s: str) -> str:
        d = unicodedata.normalize("NFKD", s)
        return "".join(c for c in d if not unicodedata.combining(c)).casefold()

    q = norm(query)
    hits: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            txt = page.extract_text() or ""
        except Exception:
            continue
        lower = norm(txt)
        start = 0
        while True:
            j = lower.find(q, start)
            if j == -1:
                break
            a, b = max(0, j - context), min(len(txt), j + len(query) + context)
            snippet = txt[a:b].replace("\n", " ")
            hits.append(f"стр. {i + 1}: ...{snippet}...")
            start = j + len(query)
            if len(hits) >= 30:
                break
        if len(hits) >= 30:
            break
    if not hits:
        return f"«{query}» не найдено в {p}"
    return _maybe_trim("pdf_search", f"{len(hits)} совпадений:\n" + "\n".join(hits))


if __name__ == "__main__":
    mcp.run()
