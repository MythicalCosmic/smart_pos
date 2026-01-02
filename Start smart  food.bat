@echo off
title Smart Food Server
color 0A

echo.
echo  ========================================
echo       SMART FOOD - Server Manager
echo  ========================================
echo.

cd /d "%~dp0"

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo  [ERROR] Python topilmadi!
    echo.
    echo  Python o'rnatilmagan. Iltimos Python 3.10+ o'rnating.
    echo  https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo  [OK] Python topildi
python --version
echo.

:: Check if virtual environment exists
if exist "venv\Scripts\activate.bat" (
    echo  [OK] Virtual environment topildi
    call venv\Scripts\activate.bat
) else (
    echo  [INFO] Virtual environment yaratilmoqda...
    python -m venv venv
    call venv\Scripts\activate.bat
    
    echo  [INFO] Kutubxonalar o'rnatilmoqda...
    pip install -r requirements.txt
)

echo.
echo  ========================================
echo       Server ishga tushirilmoqda...
echo  ========================================
echo.
echo  Client display:  http://localhost:8000/display/
echo  Chef display:    http://localhost:8000/display/chef/
echo  Admin API:       http://localhost:8000/api/
echo.
echo  To'xtatish uchun Ctrl+C bosing
echo  ========================================
echo.

python manage.py runserver 0.0.0.0:8000

pause