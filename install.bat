@echo off
chcp 65001 >nul
title Smart Jowi - O'rnatish

echo.
echo  ╔═══════════════════════════════════════╗
echo  ║     SMART JOWI - O'RNATISH            ║
echo  ╚═══════════════════════════════════════╝
echo.

cd /d "%~dp0"

echo  [1/4] Python tekshirilmoqda...
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  ╔═══════════════════════════════════════╗
    echo  ║  XATOLIK: Python topilmadi!           ║
    echo  ╚═══════════════════════════════════════╝
    echo.
    echo  Python o'rnatish uchun:
    echo.
    echo  1. https://www.python.org/downloads/ saytiga kiring
    echo  2. "Download Python" tugmasini bosing
    echo  3. O'rnatishda "Add Python to PATH" ni ALBATTA belgilang!
    echo  4. O'rnatib bo'lgach, kompyuterni qayta yoqing
    echo  5. Keyin bu faylni qayta ishga tushiring
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo  ✓ Python topildi: %PYTHON_VERSION%
echo.

echo  [2/4] Virtual environment yaratilmoqda...
echo.

if exist ".venv" (
    echo  ✓ Virtual environment allaqachon mavjud
) else (
    echo  Virtual environment yaratilmoqda...
    python -m venv .venv
    if errorlevel 1 (
        echo  ╔═══════════════════════════════════════╗
        echo  ║  XATOLIK: Venv yaratib bo'lmadi!      ║
        echo  ╚═══════════════════════════════════════╝
        pause
        exit /b 1
    )
    echo  ✓ Virtual environment yaratildi
)
echo.

echo  [3/4] Virtual environment faollashtirilmoqda...
echo.

call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo  ╔═══════════════════════════════════════╗
    echo  ║  XATOLIK: Venv faollashtirb bo'lmadi! ║
    echo  ╚═══════════════════════════════════════╝
    pause
    exit /b 1
)
echo  ✓ Virtual environment faollashtirildi
echo.

echo  [4/4] Paketlar o'rnatilmoqda...
echo.
echo  Bu biroz vaqt olishi mumkin, iltimos kuting...
echo.

if not exist "requirements.txt" (
    echo  ╔═══════════════════════════════════════╗
    echo  ║  XATOLIK: requirements.txt topilmadi! ║
    echo  ╚═══════════════════════════════════════╝
    pause
    exit /b 1
)

pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo  ╔═══════════════════════════════════════╗
    echo  ║  XATOLIK: Paketlar o'rnatilmadi!      ║
    echo  ╚═══════════════════════════════════════╝
    echo.
    echo  Internet aloqangizni tekshiring va qayta urinib ko'ring.
    pause
    exit /b 1
)

echo.
echo  ╔═══════════════════════════════════════╗
echo  ║  ✓ O'RNATISH MUVAFFAQIYATLI YAKUNLANDI ║
echo  ╚═══════════════════════════════════════╝
echo.
echo  Keyingi qadam:
echo  setup_database.bat ni ishga tushiring
echo.
pause