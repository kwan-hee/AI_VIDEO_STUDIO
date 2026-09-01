@echo off
chcp 65001 >nul
title 플레이리스트 스튜디오
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

echo.
echo   플레이리스트 스튜디오를 시작합니다...
echo.

%PY% -m playlist_studio serve --open
if errorlevel 1 (
    echo.
    echo   실행에 실패했습니다.
    echo   처음이라면 아래를 먼저 한 번 실행하세요:
    echo.
    echo     python -m venv .venv
    echo     .venv\Scripts\pip install -r requirements.txt
    echo.
)
pause
