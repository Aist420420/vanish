@echo off
chcp 65001 >nul
rem Vanish: double-click to analyze the archive in data\ (first run) and open the app.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m vanish %*
) else (
    python -m vanish %*
)
if %errorlevel%==9009 (
    echo.
    echo Не найден Python. Установите Python 3.10+ с https://www.python.org/downloads/
    echo и при установке отметьте "Add python.exe to PATH".
)
if errorlevel 1 pause
