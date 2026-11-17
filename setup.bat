@echo off
rem One-time setup on a new Windows machine: creates .venv and installs dependencies.
rem Needs Python 3.10+ on PATH and an internet connection.
cd /d "%~dp0"
python -m venv .venv || (echo Python not found. Install it from python.org and tick "Add to PATH". & pause & exit /b 1)
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt || (echo Install failed. & pause & exit /b 1)
.venv\Scripts\python -c "from mindrove.board_shim import BoardShim; print('Setup OK. Now run run.bat')"
pause
