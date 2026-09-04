# AI4TAI — архитектура

Инженерный обзор для правок и диагностики без чтения всего кода.

## Уровни

```
┌────────────────────────────────────────────────────────────────┐
│ 1. Пользователь                                                │
│    ai4tai [session|run] [-m model] [--mode ...] [--site ...]   │
└──────────────────────────────┬─────────────────────────────────┘
                               │ bin/ai4tai.bat (Windows) / bin/ai4tai (POSIX)
┌──────────────────────────────▼─────────────────────────────────┐
│ 2. bin/ai4tai.py                                               │
│    - читает .env (stdlib)                                      │
│    - GOOSE_PROVIDER=openai, GOOSE_MODEL=gpt://<folder>/<slug>  │
│    - recipes/ai4tai.yaml: instructions → tempfile →            │
│      GOOSE_SYSTEM_PROMPT_FILE_PATH; extensions → --with-*      │
│    - pre-flight: bin/ai4tai-mcp → tools/list (≥10 инструментов)│
│    - src/token_proxy.py на 127.0.0.1:<port>; OPENAI_HOST → proxy│
│    - goose session|run --no-profile                            │
└──────────────┬───────────────────────────────┬─────────────────┘
               │ subprocess                    │ stdio JSON-RPC (MCP)
┌──────────────▼──────────────┐   ┌────────────▼────────────────┐
│ 3. .tools/goose             │   │ 4. src/ai4tai_mcp.py        │
│    ReAct-цикл, tool calls,  │   │    FastMCP("ai4tai")        │
│    auto-compaction          │   │    17 инструментов          │
└──────────────┬──────────────┘   └───┬─────┬─────┬─────┬───────┘
               │ HTTP                 │     │     │     │
┌──────────────▼──────────────┐       │     │     │     │
│ 5. src/token_proxy.py       │       ▼     ▼     ▼     ▼
│    → llm.api.cloud.yandex.net│   сайт   SQLite  RAG   web/pdf
│    usage.total_tokens → файл│  (live/  demo   .rag/  DDG,
│    429 при лимите           │   mock)  .sqlite index requests
└─────────────────────────────┘
```

## Компоненты

### bin/ai4tai.py

- `.env` читается стандартной библиотекой; значения в кавычках допустимы
  (токен сайта содержит `|`).
- Модель: `-m` → алиас (`qwen`, `qwen235`, `deepseek`, `gptoss`) или slug;
  иначе `YANDEX_CLOUD_MODEL`; иначе `qwen3.6-35b-a3b/latest`.
- Контекст: `GOOSE_CONTEXT_LIMIT` (по умолчанию 128k), auto-compact при
  100k токенов.
- Режим по умолчанию: `smart_approve` в сессии, `auto` в `run`.
- Pre-flight probe MCP через shim; при сбое — exit 3 с подсказкой.
- Windows: shim `bin\ai4tai-mcp.bat` подставляется автоматически.

### recipes/ai4tai.yaml

Goose recipe: `extensions` (builtin `developer` + stdio `ai4tai`) и
`instructions` — системный промпт: идентичность, петля недоверия,
видимость работы, стиль, skills, инструменты, запреты.

### src/ai4tai_mcp.py

Один stdio-процесс. Группы инструментов и их зависимости:

| Группа | Инструменты | Зависимости |
|---|---|---|
| Служебные | `token_budget`, `load_artifact`, `list_skills`, `load_skill` | файлы |
| Сайт | `site_status`, `site_search`, `site_product`, `site_categories` | `requests` → `TARU_BASE_URL`; fallback `data/catalog_mock.json` |
| База | `sqlite_schema`, `sqlite_query` | `sqlite3`; `demo_db.build()` при отсутствии базы |
| RAG | `rag_status`, `rag_search` | `rag_index` |
| Веб | `web_search`, `web_fetch` | DuckDuckGo HTML / Brave API |
| PDF | `pdf_info`, `pdf_read`, `pdf_search` | `pypdf` |

Режимы сайта (`AI4TAI_SITE_MODE`):
- `auto` — при наличии `TARU_API` запрос к API; ответ не JSON (капча,
  HTML, ошибка) → локальная копия с пометкой; без токена — сразу локальная
  копия.
- `live` — только API, ошибки возвращаются как `ERROR`.
- `mock` — только локальная копия. Используется в тестах.

`sqlite_query` открывает базу в режиме `mode=ro` для SELECT/WITH/PRAGMA/
EXPLAIN; остальные операторы отклоняются без `AI4TAI_DB_WRITE=1`.

Тяжёлые результаты (> 800 символов) усекаются до превью + `artifact_id`;
полный текст — `load_artifact`. Артефакты живут в памяти процесса.

### src/rag_index.py

- Нарезка по строкам до ~900 символов с перекрытием 2 строки.
- Эмбеддеры: `YandexEmbedder` (`/v1/embeddings`, `emb://<folder>/
  text-search-doc|query/latest`), `HashEmbedder` (bag-of-words с
  биграммами, dim 512, без сети).
- Индекс — SQLite: `meta`, `docs`, `chunks` (вектор float32 BLOB).
  Имя эмбеддера хранится в `meta`; поиск использует тот же.
- Поиск — косинус в Python; для учебных объёмов (сотни фрагментов)
  достаточно.

### src/demo_db.py

Детерминированная генерация (seed 20260908): 35 позиций номенклатуры из
каталога, 4 склада, остатки, 8 клиентов, ~60 заказов за 60 дней.

### src/token_proxy.py

HTTP-прокси на localhost: пересылает запросы в Yandex, читает
`usage.total_tokens` (включая SSE), пишет `~/.ai4tai_budget.json`,
возвращает 429 при превышении `AI4TAI_DAILY_TOKEN_LIMIT`.

## Жизненный цикл сессии

1. `bin/ai4tai.bat` → `bin/ai4tai.py`.
2. `.env` → окружение; recipe → системный промпт и флаги расширений.
3. Pre-flight probe MCP.
4. Старт token proxy, чтение порта из stdout.
5. Баннер: модель, контекст, режим, сайт, бюджет.
6. `goose session --no-profile --with-builtin developer --with-extension "<shim>"`.
7. Goose: при старте — `tools/list` у MCP; каждый turn — LLM → tool calls
   → результаты в контекст.
8. Выход: proxy останавливается, временный файл промпта удаляется.

## Ограничения

- Модель `qwen3.6-35b-a3b` возвращает `reasoning_content`; Goose
  использует `content` и tool calls, размышления не отображаются.
- Yandex API отвечает `HTTP 429` при превышении квоты folder — Goose
  показывает ошибку провайдера; повтор через минуту.
- API technoavia.ru за защитой от ботов может отдавать HTML вместо JSON.
  В режиме `auto` это переводит инструмент на локальную копию.
- Смена модели внутри сессии не поддерживается: перезапуск с `-m`.
- Режим `run` использует `--no-session`: одноразовые запуски не пишут в
  базу сессий Goose (`sessions.db`). База сессий от старых версий Goose
  может быть несовместима с 1.49 — при panic в `sqlx-sqlite` в режиме
  `session` переименовать `~/.local/share/goose/sessions/` (POSIX) или
  `%LOCALAPPDATA%\Block\goose\data\sessions\` (Windows).
- Версия Goose закреплена в `setup.py` (`v1.49.0`); другая версия —
  `AI4TAI_GOOSE_RELEASE=<url релиза>`.

## Отладка

- `ai4tai doctor` — ключ, Goose, venv, база, индекс, MCP probe, бюджет.
- Прямой запуск MCP: `.venv\Scripts\python.exe src\ai4tai_mcp.py` (ждёт
  stdin).
- Логи Goose: `~/.local/state/goose/logs/` (POSIX) или
  `%LOCALAPPDATA%\Block\goose\` (Windows).
- Пропуск pre-flight: `AI4TAI_SKIP_PREFLIGHT=1`.
- Тесты: `pytest tests -v`; сетевые — `AI4TAI_TEST_NETWORK=1`.
