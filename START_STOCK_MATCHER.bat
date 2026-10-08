@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Stock Script Matcher

set "PY_CMD="
where py >nul 2>nul
if not errorlevel 1 (
    py -3.10 -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
    if not errorlevel 1 set "PY_CMD=py -3.10"
)
if not defined PY_CMD (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
        if not errorlevel 1 set "PY_CMD=python"
    )
)
if not defined PY_CMD (
    echo [ERROR] Khong tim thay Python 3.10 tro len.
    echo Hay cai Python va tick "Add Python to PATH".
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Tao virtual environment...
    %PY_CMD% -m venv .venv
    if errorlevel 1 goto :failed
)

call ".venv\Scripts\activate.bat"

if not exist ".venv\.stock_matcher_installed" (
    echo [2/4] Cai dependencies lan dau...
    python -m pip install --upgrade pip
    if errorlevel 1 goto :failed
    python -m pip install -r requirements.txt
    if errorlevel 1 goto :failed
    echo installed>".venv\.stock_matcher_installed"
) else (
    echo [2/4] Dependencies da san sang.
)

if not exist ".env" (
    echo [3/4] Tao file cau hinh .env...
    copy /Y ".env.example" ".env" >nul
) else (
    echo [3/4] Da co file .env.
)

echo [4/4] Khoi dong service theo HOST/PORT trong file .env
python run_server.py

echo.
echo Service da dung.
pause
exit /b 0

:failed
echo.
echo [ERROR] Cai dat hoac khoi dong that bai. Xem log phia tren.
pause
exit /b 1
