@echo off
REM AI4TAI setup — Windows. Делегирует в setup.py.
setlocal
set "REPO=%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
python "%REPO%setup.py" %*
endlocal
