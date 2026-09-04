# Свой MCP-сервер за 10 минут

1. Скопировать `s01_hello.py` в свой проект, например `my_tools.py`.
2. Добавить функцию с декоратором `@mcp.tool()`. Аргументы типизированы,
   docstring описывает, что делает инструмент и что возвращает.
3. Проверить, что сервер запускается и отдаёт список инструментов:

   ```powershell
   ..\AI4TAI\.venv\Scripts\python.exe my_tools.py
   ```

   Сервер ждёт ввода — это нормально. `Ctrl-C` для выхода.

4. Подключить к агенту. В `recipes/ai4tai.yaml` (или в копии recipe
   в своём проекте) добавить расширение:

   ```yaml
   extensions:
     - type: builtin
       name: developer
     - type: stdio
       name: ai4tai
       cmd: bin/ai4tai-mcp
       timeout: 180
     - type: stdio
       name: my-tools
       cmd: .venv/Scripts/python.exe
       args: ["C:/projects/my/my_tools.py"]
       timeout: 60
   ```

   Путь `cmd` относительный к корню AI4TAI, `args` — абсолютный путь
   к файлу сервера.

5. Запустить агента и попросить: «вызови hello» или «проверь доступность
   msk-app20 через ping_host». Агент видит инструмент по имени и docstring.

Проверка: в ответе агента есть результат вызова, в `DIARY.md` — запись
с запросом, результатом и способом проверки.
