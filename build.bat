@echo off
rem Builds dist\Proxion.exe. Needs Python 3.12+ from python.org on PATH.
cd /d "%~dp0"
py -3 -m venv .buildenv || goto :fail
.buildenv\Scripts\python -m pip install --upgrade pip
.buildenv\Scripts\python -m pip install -r requirements.txt pyinstaller || goto :fail
.buildenv\Scripts\pyinstaller --noconfirm proxion.spec || goto :fail
echo.
echo Done: dist\Proxion.exe
pause
goto :eof
:fail
echo Build failed.
pause
