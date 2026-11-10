@echo off
setlocal
cd /d "%~dp0.."

python -m pip install --upgrade pip pyinstaller
python -m PyInstaller --noconfirm --clean ^
  --windowed ^
  --name Assist ^
  --add-data "assist;assist" ^
  main.py

echo.
echo Built: dist\Assist\Assist.exe
echo Copy the dist\Assist folder to run Assist on Windows.
endlocal
