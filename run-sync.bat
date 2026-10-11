@echo off
setlocal
cd /d "%~dp0"

if not exist "config\run.local.bat" (
    echo Copy config\run.local.example.bat to config\run.local.bat and configure it.
    exit /b 1
)
call "config\run.local.bat"

".venv\Scripts\python.exe" gmail_billing.py --output "output\m365_billing.csv"
if errorlevel 1 exit /b 1

".venv\Scripts\python.exe" inventory_sync.py --live --billing "output\m365_billing.csv" --publish
if errorlevel 1 exit /b 1

exit /b 0
