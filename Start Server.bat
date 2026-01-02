@echo off
title Smart Food Server

echo.
echo  ================================
echo    SMART FOOD - Server
echo  ================================
echo.

cd /d "%~dp0"

echo  Serverни ишга туширилмоқда...
echo.

python manage.py runserver 0.0.0.0:8000

pause