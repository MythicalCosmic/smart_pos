@echo off
chcp 65001 >nul
title Smart Jowi - Server

echo.
echo  ╔═══════════════════════════════════════╗
echo  ║        SMART JOWI - SERVER            ║
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

echo  Virtual environment faollashtirilmoqda...
call .venv\Scripts\activate.bat
echo  ✓ Faollashtirildi
echo.

echo  Telegram Bot ishga tushirilmoqda...
start /B cmd /c ".venv\Scripts\python.exe manage.py run_bot >nul 2>&1"
echo  ✓ Bot ishga tushdi
echo.

echo  Order Notification ishga tushirilmoqda...
start /B cmd /c ".venv\Scripts\python.exe manage.py order_proccess_notification --daemon --interval 30 >nul 2>&1"
echo  ✓ Order Notification ishga tushdi
echo.

echo  Shift Notifier ishga tushirilmoqda...
start /B cmd /c ".venv\Scripts\python.exe manage.py run_shift_notifier --interval 30 >nul 2>&1"
echo  ✓ Shift Notifier ishga tushdi
echo.

echo  ╔═══════════════════════════════════════╗
echo  ║  Server ishga tushirilmoqda...        ║
echo  ║  Manzil: http://localhost:8000        ║
echo  ╚═══════════════════════════════════════╝
echo.
echo  3 sekunddan keyin oyna yashirinadi...
echo  To'xtatish uchun: stop.bat
echo.

timeout /t 3 /nobreak >nul

powershell -ExecutionPolicy Bypass -Command "Add-Type @'`nusing System;`nusing System.Runtime.InteropServices;`npublic class W{[DllImport(\"user32.dll\")]public static extern bool ShowWindow(IntPtr h,int c);[DllImport(\"kernel32.dll\")]public static extern IntPtr GetConsoleWindow();}`n'@;[W]::ShowWindow([W]::GetConsoleWindow(),6)|Out-Null"

python manage.py runserver 0.0.0.0:8000 --nothreading