# AI4TAI

![CI](https://github.com/andkhalov/AI4TAI/actions/workflows/test.yml/badge.svg)
![Windows](https://img.shields.io/badge/Windows-10%2F11-brightgreen)
![macOS](https://img.shields.io/badge/macOS-supported-brightgreen)
![Linux](https://img.shields.io/badge/Linux-supported-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue)

Учебный консольный агент интенсива **«AI4TAI — агентная разработка для
ИТ-департамента»** (Техноавиа, сентябрь 2026). Автор курса — А. П. Халов.

AI4TAI — тонкая обёртка над открытым агентом [Goose](https://github.com/block/goose)
с инференсом через Yandex AI Studio. Устанавливается на Windows без WSL.
Внутри — один MCP-сервер с инструментами для задач ИТ-департамента:
каталог сайта technoavia.ru, учебная SQLite-база «номенклатура / остатки /
заказы», RAG по документам, интернет-поиск, чтение PDF, модульные skills
(PowerShell, запросы 1С, SQLite, React, Python).

Форк учебного агента [AI4Math](https://github.com/andkhalov/AI4Math) (ШАД, 2026).

---

## Установка

### Windows 10/11 (основной путь)

Нужны: Python 3.10+ (с галочкой «Add to PATH»), git. Ключ Yandex AI Studio
выдаётся на курсе.

```powershell
git clone https://github.com/andkhalov/AI4TAI.git
cd AI4TAI
setup.bat
```

`setup.bat` создаёт `.venv`, ставит зависимости, скачивает Goose в
`.tools\`, спрашивает ключ и folder id (wizard), собирает учебную базу и
запускает проверку `doctor`. Повторный запуск безопасен.

Запуск:

```powershell
bin\ai4tai.bat                    # интерактивная сессия
bin\ai4tai.bat run "промпт"       # одна задача и выход
bin\ai4tai.bat doctor             # проверка окружения
```

Для команды `ai4tai` без пути: добавить `<папка>\AI4TAI\bin` в PATH.

### macOS / Linux

```bash
git clone https://github.com/andkhalov/AI4TAI.git && cd AI4TAI && ./setup.sh
```

После установки команда `ai4tai` доступна через `~/.local/bin`.

### Ручная настройка `.env`

Скопировать `.env.example` в `.env` и заполнить:

```
YANDEX_CLOUD_API_KEY=...
YANDEX_CLOUD_FOLDER=b1g...
YANDEX_CLOUD_MODEL=qwen3.6-35b-a3b/latest
```

Токен сайта `TARU_API` необязателен. Без него инструменты сайта работают
с локальной копией каталога `src/fixtures/catalog_mock.json`. Токен содержит
символ `|`, в `.env` он записывается в кавычках.

---

## Использование

| Команда | Действие |
|---|---|
| `ai4tai` | Интерактивная сессия, режим `smart_approve` |
| `ai4tai run "<промпт>"` | Одна задача без подтверждений, выход |
| `ai4tai doctor` | Проверка: ключ, Goose, venv, база, MCP-сервер, бюджет |
| `ai4tai -m <slug\|alias>` | Модель: `qwen` (по умолчанию), `junior` (домашний режим, дешёвая gpt-oss-20b), `qwen235`, `deepseek`, `gptoss` или полный slug |
| `ai4tai --mode approve` | Каждый вызов инструмента требует подтверждения |
| `ai4tai --site mock` | Сайт только из локальной копии |

Slash-команды в сессии: `/plan <задача>`, `/mode <auto|smart_approve|approve|chat>`,
`/summary`, `/exit`, `/help`. `Ctrl-C` прерывает текущее действие,
`Ctrl-C` дважды — выход.

Режимы подтверждения:

| Режим | Поведение |
|---|---|
| `smart_approve` | Чтение автоматически; запись и выполнение команд — с подтверждением |
| `auto` | Все вызовы без подтверждений |
| `approve` | Каждый вызов с подтверждением |
| `chat` | Без инструментов |

---

## Инструменты MCP-сервера

| Инструмент | Назначение |
|---|---|
| `site_search(query, limit)` | Поиск товара на technoavia.ru по названию, категории, свойству, артикулу |
| `site_product(sku)` | Карточка товара: свойства, цена, описание, ссылка |
| `site_categories()` | Категории каталога |
| `site_status()` | Режим (live / mock), наличие токена, доступность API |
| `sqlite_schema(db_path)` | Таблицы и колонки базы |
| `sqlite_query(sql, db_path, max_rows)` | SELECT к базе; запись при `AI4TAI_DB_WRITE=1` |
| `rag_search(query, top_k)` | Поиск фрагментов в индексе документов с указанием файла и строк |
| `rag_status()` | Состояние индекса |
| `web_search(query, n)` | DuckDuckGo или Brave (при `BRAVE_API_KEY`) |
| `web_fetch(url)` | Текст страницы |
| `pdf_info`, `pdf_read`, `pdf_search` | Локальные PDF |
| `list_skills()`, `load_skill(name)` | Модульные инструкции из `skills/` |
| `token_budget()`, `load_artifact(id)` | Расход токенов; полный текст усечённого результата |

Файлы и команды — встроенные инструменты Goose (`developer`): `shell`, `write`, `edit`, `tree`, `read_image`.

### Сайт technoavia.ru

`AI4TAI_SITE_MODE`: `auto` (по умолчанию) — API при наличии токена, при
сбое или ответе не в JSON — локальная копия; `live` — только API; `mock` —
только локальная копия. Источник указывается в каждом ответе инструмента.

### Учебная база

`.data/demo.sqlite` собирается при установке из `src/demo_db.py`
детерминированно. Таблицы: `nomenclature`, `warehouses`, `stock`,
`customers`, `orders`, `order_items`. Артикулы совпадают с каталогом сайта.

### RAG

```powershell
.venv\Scripts\python.exe src\rag_index.py index data\docs --db .rag\index.sqlite
.venv\Scripts\python.exe src\rag_index.py search "срок носки каски" --db .rag\index.sqlite
```

Эмбеддинги: Yandex (`text-search-doc` / `text-search-query`) при наличии
ключа; `--embedder hash` — локальный вариант без сети. Индексируются
`.md .txt .csv .json .log .ps1 .py .sql .bsl .yaml .pdf`.

---

## Skills

| Skill | Область |
|---|---|
| `powershell` | Скрипты для Windows Server: диски, службы, журналы, удалённое выполнение |
| `1c-query` | Чтение и оптимизация запросов 1С |
| `sqlite` | Работа с базой через `sqlite_schema` / `sqlite_query` |
| `react` | Компоненты витрины на React + TypeScript |
| `python` | Скрипты и MCP-инструменты |
| `debug-loop` | Цикл написал → запустил → прочитал вывод → исправил |
| `markdown` | AGENT.md, DIARY.md, CONTEXT.md, документация |

Свой skill: файл `skills/<имя>.md` с frontmatter (`name`, `description`,
`triggers`, `combines_with`). Дополнительная папка — `AI4TAI_SKILLS_DIR`.

---

## Учебные данные и материалы курса

| Что | Где |
|---|---|
| Задачи «найди ошибку» | `tasks/day1/` в этом репозитории |
| Шаблоны памяти проекта | `templates/` |
| Шаблон своего MCP-сервера | `templates/mcp/` |
| Локальная копия каталога сайта | `src/fixtures/catalog_mock.json` (фикстура кода, нужна режиму mock) |
| Учебная база | `.data/demo.sqlite`, собирается при установке |
| Документы для RAG, раздатка, выгрузки для практики | выдаются на занятии отдельным комплектом; в репозитории агента их нет |

Индексация своих или учебных документов:

```powershell
.venv\Scripts\python.exe src\rag_index.py index <папка с документами> --db .rag\index.sqlite
```

---

## Устройство

```
bin/ai4tai.py         обёртка: .env → окружение Goose → recipe → token proxy → goose session|run
recipes/ai4tai.yaml   системный промпт агента + список расширений
src/ai4tai_mcp.py     MCP-сервер (stdio), все инструменты
src/rag_index.py      RAG: нарезка, эмбеддинги, SQLite-индекс, поиск
src/demo_db.py        генератор учебной базы
src/token_proxy.py    локальный прокси к Yandex, учёт токенов, суточный лимит
cli/wizard.py         настройка .env
skills/               модульные инструкции
```

Подробнее — `docs/ARCHITECTURE.md`.

Суточный лимит — 3 000 000 токенов на установку (`AI4TAI_DAILY_TOKEN_LIMIT`).
Счётчик в `~/.ai4tai_budget.json`, сброс в полночь.

---

## Тесты

```powershell
.venv\Scripts\python.exe -m pip install pytest
.venv\Scripts\python.exe -m pytest tests -v
```

Юнит-тесты не ходят в сеть: сайт в режиме `mock`, база во временной
папке, RAG на hash-эмбеддере. Сетевые тесты — `AI4TAI_TEST_NETWORK=1`.

CI (GitHub Actions) на каждый push: юнит-тесты на Ubuntu, Windows и
macOS; установка с нуля и `doctor` на Ubuntu и Windows; сквозной прогон
задачи через агента на Ubuntu и Windows при заданных секретах
`YANDEX_CLOUD_API_KEY`, `YANDEX_CLOUD_FOLDER`.

---

## Обновление и удаление

```powershell
git pull
Remove-Item -Recurse -Force .venv, .tools
setup.bat
```

`.env` сохраняется. Удаление — удалить папку репозитория и файл
`~/.ai4tai_budget.json`.

## Лицензия

MIT.
