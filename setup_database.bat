@echo off
chcp 65001 >nul
title APP - Ma'lumotlar Bazasi

echo.
echo  ╔═══════════════════════════════════════╗
echo  ║  SMART JOWI - MA'LUMOTLAR BAZASI      ║
echo  ╚═══════════════════════════════════════╝
echo.

cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo  ╔═══════════════════════════════════════╗
    echo  ║  XATOLIK: Virtual environment yo'q!   ║
    echo  ╚═══════════════════════════════════════╝
    echo.
    echo  Avval install.bat ni ishga tushiring!
    echo.
    pause
    exit /b 1
)

echo  [1/3] Virtual environment faollashtirilmoqda...
call .venv\Scripts\activate.bat
echo  ✓ Faollashtirildi
echo.

echo  [2/3] Migratsiyalar yaratilmoqda...
echo.
python manage.py makemigrations
if errorlevel 1 (
    echo.
    echo  ╔═══════════════════════════════════════╗
    echo  ║  XATOLIK: Makemigrations bajarilmadi! ║
    echo  ╚═══════════════════════════════════════╝
    pause
    exit /b 1
)
echo.
echo  ✓ Migratsiyalar yaratildi
echo.

echo  [3/3] Ma'lumotlar bazasi yangilanmoqda...
echo.
python manage.py migrate
if errorlevel 1 (
    echo.
    echo  ╔═══════════════════════════════════════╗
    echo  ║  XATOLIK: Migrate bajarilmadi!        ║
    echo  ╚═══════════════════════════════════════╝
    pause
    exit /b 1
)
echo.
echo  ✓ Ma'lumotlar bazasi yangilandi
echo.

echo  ╔═══════════════════════════════════════╗
echo  ║  ✓ BAZA MUVAFFAQIYATLI SOZLANDI       ║
echo  ╚═══════════════════════════════════════╝
echo.
echo  Keyingi qadam:
echo  start.bat ni ishga tushiring
echo.
pause