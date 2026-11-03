@echo off
title Site Mockup Maker by Raddito
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" goto run

call :findpy
if not defined PY (
  echo  Python is not installed. Installing Python 3.12 for your user, one time only...
  winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
  call :findpy
)
if not defined PY (
  echo.
  echo  Could not install Python automatically.
  echo  1. Download it from https://www.python.org/downloads/
  echo  2. During install, TICK "Add python.exe to PATH"
  echo  3. Then double-click this file again.
  pause
  exit /b
)
echo  First run: installing what the program needs. This takes a few minutes, only once.
"%PY%" -m venv .venv
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check playwright pillow
".venv\Scripts\python.exe" -m playwright install chromium

:run
start "" ".venv\Scripts\pythonw.exe" app.pyw
exit /b

:findpy
set "PY="
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python313\python.exe" "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" "%ProgramFiles%\Python313\python.exe" "%ProgramFiles%\Python312\python.exe") do (
  if not defined PY if exist %%P set "PY=%%~P"
)
if not defined PY (
  python -c "import sys" >nul 2>nul && for /f "delims=" %%Q in ('python -c "import sys;print(sys.executable)"') do set "PY=%%Q"
)
exit /b
