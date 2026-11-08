@echo off
cd /d "%~dp0"
if not exist .venv (
  py -3 -m venv .venv || goto :nopython
  .venv\Scripts\python -m pip install -r requirements.txt
)
start "" .venv\Scripts\pythonw -m proxion
goto :eof
:nopython
echo Python 3.12+ is needed. Get it from https://www.python.org/downloads/ and tick "Add to PATH".
pause
