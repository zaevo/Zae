@echo off
REM One-step launcher for Windows. Double-click this file.
REM Creates a local virtualenv, installs deps, starts BreachCheck on 127.0.0.1:8787.
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python not found. Install it from https://python.org (tick "Add to PATH"^) and re-run.
  pause
  exit /b 1
)

if not exist ".venv" (
  echo ^>^> creating virtualenv...
  python -m venv .venv
)

call .venv\Scripts\activate.bat
echo ^>^> installing dependencies...
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt

echo ^>^> starting BreachCheck at http://127.0.0.1:8787  (close this window to stop)
start "" http://127.0.0.1:8787
python app.py
pause
