# Assist

Light Windows desktop app for daily work across places — local time and weather, with quick add/remove.

## Features

- Live local time for each saved place
- Current weather (Open-Meteo, no API key)
- Add places by city search
- Remove places in one click
- Places saved on this PC (`%USERPROFILE%\.assist\places.json`)

## Requirements

- Windows 10/11
- Python 3.10+ (python.org installer includes `tkinter`)

## Run

```bat
python main.py
```

Or double-click `scripts\run-assist.bat`.

## Build a Windows app folder

```bat
scripts\build-windows.bat
```

Then run `dist\Assist\Assist.exe`.

## Light footprint

- No web server, no Electron, no Node
- Stdlib UI (`tkinter`) + HTTPS weather calls
- Optional PyInstaller only when packaging
