@echo off
setlocal
title Site Mockup Maker by Raddito
cd /d "%~dp0"

rem ---- running from inside a ZIP file does not work
echo "%~dp0" | findstr /i "\\Temp\\" >nul && (
  echo.
  echo  Please unzip the folder first: right-click the ZIP file, choose "Extract All",
  echo  then open START-WINDOWS.bat from the extracted folder.
  pause
  exit /b 1
)

if exist ".venv\ready.flag" goto run

echo  Site Mockup Maker by Raddito - first-time setup
echo  Folder: %CD%
echo.

call :findpy
if not defined PY (
  echo  Python is not installed. Trying to install Python 3.12 for you, one time only...
  where winget >nul 2>nul
  if errorlevel 1 (
    echo  winget is not available on this PC.
  ) else (
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
  )
  call :findpy
)
if not defined PY (
  echo.
  echo  Could not install Python automatically.
  echo  1. Download Python 3.12 from https://www.python.org/downloads/
  echo  2. During install, TICK "Add python.exe to PATH"
  echo  3. Then double-click this file again.
  pause
  exit /b 1
)

echo  Using Python: %PY%
echo  Installing what the program needs. This takes a few minutes, only once.
echo  Please keep this window open until the program opens.
echo.
if exist ".venv" rmdir /s /q ".venv"
echo  Step 1 of 4: creating the program environment
"%PY%" -m venv .venv
if errorlevel 1 goto fail
if not exist ".venv\Scripts\python.exe" goto fail
echo  Step 2 of 4: installing Pillow and Playwright
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check playwright pillow
if errorlevel 1 goto fail
echo  Step 3 of 4: installing the browser used for screenshots
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto fail
echo  Step 4 of 4: checking
".venv\Scripts\python.exe" -c "import tkinter, PIL, playwright"
if errorlevel 1 goto fail
echo ok> ".venv\ready.flag"

:run
start "" ".venv\Scripts\pythonw.exe" app.pyw
exit /b 0

:fail
echo.
echo  ------------------------------------------------------------
echo  Setup did not finish. Take a screenshot of this window and send it to Raddito.
echo  Python used: %PY%
echo  Then close this window and double-click START-WINDOWS.bat to try again.
echo  ------------------------------------------------------------
pause
exit /b 1

:findpy
set "PY="
rem 1. the Python launcher (installed by python.org)
for /f "delims=" %%Q in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do if not defined PY if exist "%%Q" set "PY=%%Q"
rem 2. usual install folders
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python313\python.exe" "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" "%ProgramFiles%\Python313\python.exe" "%ProgramFiles%\Python312\python.exe" "%ProgramFiles%\Python311\python.exe") do (
  if not defined PY if exist %%P set "PY=%%~P"
)
rem 3. python on the PATH (not the Microsoft Store shortcut)
if not defined PY (
  for /f "delims=" %%Q in ('python -c "import sys;print(sys.executable)" 2^>nul') do if not defined PY if exist "%%Q" set "PY=%%Q"
)
exit /b 0
