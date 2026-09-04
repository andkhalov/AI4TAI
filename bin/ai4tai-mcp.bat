@echo off
REM AI4TAI MCP stdio server — Windows shim (mirrors bin/ai4tai-mcp).
setlocal
set "REPO=%~dp0.."
set "PY=%REPO%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%REPO%\src\ai4tai_mcp.py" %*
endlocal
