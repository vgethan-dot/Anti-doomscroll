@echo off
REM Lance AntiScroll sous Windows (Python 3 requis : python.org, cocher "Add to PATH")
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\pip install -r requirements.txt
)
start "" .venv\Scripts\pythonw.exe antiscroll.py %*
