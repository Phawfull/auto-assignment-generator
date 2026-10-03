@echo off
setlocal
cd /d "%~dp0"
set "TUTORIAL_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%TUTORIAL_PY%" (
    "%TUTORIAL_PY%" tutorial_maker.py
) else (
    py tutorial_maker.py
)
if errorlevel 1 pause
