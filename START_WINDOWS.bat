@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    python -m venv .venv
    if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe backend\app.py
pause
exit /b
:failed
echo Startup failed. Check Python installation and the error above.
pause
exit /b 1
