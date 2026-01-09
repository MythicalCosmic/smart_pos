@echo off
chcp 65001 >nul
title Smart Food Server

echo.
echo  ================================
echo    SMART FOOD - Server
echo  ================================
echo.

cd /d "%~dp0"

REM Check and activate virtual environment
set VENV_ACTIVATED=0

if exist "venv\Scripts\activate.bat" (
    echo  Virtual environment topildi: venv
    call venv\Scripts\activate.bat
    set VENV_ACTIVATED=1
) else if exist ".venv\Scripts\activate.bat" (
    echo  Virtual environment topildi: .venv
    call .venv\Scripts\activate.bat
    set VENV_ACTIVATED=1
) else if exist "env\Scripts\activate.bat" (
    echo  Virtual environment topildi: env
    call env\Scripts\activate.bat
    set VENV_ACTIVATED=1
)

if %VENV_ACTIVATED%==0 (
    echo.
    echo  ========================================
    echo   XATOLIK: Virtual environment topilmadi!
    echo  ========================================
    echo.
    echo  Iltimos quyidagilardan birini yarating:
    echo    python -m venv venv
    echo    python -m venv .venv
    echo    python -m venv env
    echo.
    echo  Keyin bu faylni qayta ishga tushiring.
    echo  ========================================
    pause
    exit /b 1
)

echo  Virtual environment faollashtirildi!
echo.

REM Check if Django is installed
python -c "import django" 2>nul
if errorlevel 1 (
    echo.
    echo  ========================================
    echo   XATOLIK: Django o'rnatilmagan!
    echo  ========================================
    echo.
    echo  Django o'rnatish uchun:
    echo    pip install django
    echo.
    echo  Yoki barcha dependencylarni o'rnatish:
    echo    pip install -r requirements.txt
    echo  ========================================
    echo.
    pause
    exit /b 1
)

echo  Django topildi!
echo.
echo  Serverni ishga tushirilmoqda...
echo  Server manzili: http://localhost:8000
echo.
echo  Oyna 3 sekunddan keyin minimizatsiya qilinadi...
echo.

REM Wait 3 seconds then minimize window
timeout /t 3 /nobreak >nul

REM Minimize this window using PowerShell
powershell -ExecutionPolicy Bypass -File "%~dp0minimize_window.ps1"

echo  Oyna minimizatsiya qilindi. Taskbarda topishingiz mumkin.
echo  To'xtatish uchun: stop_server.bat ni ishga tushiring
echo  ================================
echo.
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py runserver 0.0.0.0:8000

echo.
echo  Server to'xtatildi.
pause