@echo off
REM AI4TAI entrypoint — Windows. Forwards to bin\ai4tai.py.
setlocal
set "REPO=%~dp0.."
set "PY=%REPO%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%REPO%\bin\ai4tai.py" %*
endlocal
