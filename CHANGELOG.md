# Changelog

## 1.1.0 — 2026-09-10

- Алиас модели `junior` (`gpt-oss-20b`) для работы дома с меньшим
  расходом общего лимита.
- Windows: принудительный UTF-8 в `rag_index.py`, `demo_db.py`,
  `token_proxy.py` — кириллица в консоли `cp1252` больше не роняет
  индексацию.
- Материалы курса в репозитории: `course/day1/` (чек-лист, шпаргалка,
  шаблон журнала, готовые `AGENT.md` под профили, выгрузки
  `demo_admin/` для практики по администрированию) и
  `course/show_request.py` — разбор реального запроса к модели из
  логов Goose.

## 1.0.0 — 2026-09-04

Первый выпуск AI4TAI. Форк AI4Math (ШАД, 2026) под интенсив «Агентная
разработка для ИТ-департамента» (Техноавиа).

Изменения относительно AI4Math:

- Идентичность, recipe, README и документация переписаны под аудиторию
  ИТ-департамента.
- Удалены Lean, SciLib, поиск по Mathlib, скачивание PDF, LaTeX и
  literature skills.
- Добавлены инструменты сайта technoavia.ru (`site_search`, `site_product`,
  `site_categories`, `site_status`) с локальной копией каталога.
- Добавлены `sqlite_schema` / `sqlite_query` и генератор учебной базы
  `src/demo_db.py`.
- Добавлен RAG: `src/rag_index.py` (Yandex или hash-эмбеддер),
  инструменты `rag_search` / `rag_status`.
- Skills: `powershell`, `1c-query`, `sqlite`, `react`; `python`,
  `debug-loop`, `markdown` переписаны.
- Переменные окружения: `YANDEX_CLOUD_API_KEY`, `YANDEX_CLOUD_FOLDER`,
  `YANDEX_CLOUD_MODEL`, `TARU_API`, `TARU_BASE_URL`, `AI4TAI_*`.
- Модель по умолчанию `qwen3.6-35b-a3b/latest`; выбор по алиасу или slug.
- Wizard: неинтерактивный режим из переменных окружения.
- Материалы курса: `tasks/day1/`, `data/docs/`, `templates/`.
- Тесты: сайт (mock/auto/live), SQLite, RAG, CLI, веб, PDF, skills.
  CI: юнит-тесты на Ubuntu/Windows/macOS, установка с нуля на
  Ubuntu/Windows, e2e при наличии секретов.
- Зависимость `mcp` закреплена `<2` (в 2.x переименован FastMCP).
