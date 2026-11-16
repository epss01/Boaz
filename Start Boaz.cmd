@echo off
setlocal
cd /d "%~dp0"
title Boaz

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m boaz --open-browser
) else (
    where uv >nul 2>nul
    if errorlevel 1 (
        echo Boaz needs uv. Install it using the instructions in README.md.
        pause
        exit /b 1
    )
    uv run --frozen python -m boaz --open-browser
)

if errorlevel 1 (
    echo.
    echo Boaz could not start. See the error above.
    pause
    exit /b 1
)
