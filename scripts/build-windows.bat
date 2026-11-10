@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

echo.
echo === Assist Windows build ===
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python was not found on PATH.
  echo Install Python 3.10+ from https://www.python.org/downloads/
  echo Make sure "Add python.exe to PATH" is checked.
  pause
  exit /b 1
)

echo [1/3] Installing build dependencies...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo ERROR: pip install failed.
  pause
  exit /b 1
)

echo [2/3] Building single-file Assist.exe ...
if exist build rmdir /s /q build
if exist dist\Assist.exe del /f /q dist\Assist.exe
if exist dist\Assist rmdir /s /q dist\Assist

python -m PyInstaller --noconfirm --clean Assist.spec
if errorlevel 1 (
  echo ERROR: PyInstaller build failed.
  pause
  exit /b 1
)

echo [3/3] Preparing easy-run folder...
if not exist "Release" mkdir "Release"
copy /y "dist\Assist.exe" "Release\Assist.exe" >nul
copy /y "scripts\Run Assist.bat" "Release\Run Assist.bat" >nul 2>nul

echo.
echo SUCCESS
echo   Easy run:  Release\Assist.exe
echo   Also at:   dist\Assist.exe
echo.
echo Double-click Release\Assist.exe to start Assist.
echo First launch may take a few seconds while Windows unlocks the file.
echo.
pause
endlocal
