@echo off
cd /d "%~dp0backend"
start /b python -m uvicorn main:app --host localhost --port 8000
timeout /t 3 /nobreak > nul
start "" http://localhost:8000
pause
