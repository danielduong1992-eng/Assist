# Assist

Light Windows desktop app for daily work across places — local time, weather, and a network guard that watches for strange or dangerous traffic.

## Features

- Live local time for each saved place
- Current weather (Open-Meteo, no API key)
- Add / remove places
- **Network guard**: analyzes connections (and packets when permitted); notifies you on dangerous or strange events
- Places and alerts saved on this PC (`%USERPROFILE%\.assist\`)

## Requirements

- Windows 10/11
- Python 3.10+ (python.org installer includes `tkinter`)

## Run

```bat
pip install -r requirements.txt
python main.py
```

Or double-click `scripts\run-assist.bat`.

## Network guard

- Default mode: light **connection analysis** (no admin required)
- Optional **packet capture** on Windows needs Administrator + Npcap
- Alerts appear in-app; dangerous events also trigger a desktop warning dialog
- Use **Test alert** to verify notifications

## Build a Windows app folder

```bat
scripts\build-windows.bat
```

Then run `dist\Assist\Assist.exe`.

## Light footprint

- No web server, no Electron, no Node
- Stdlib UI (`tkinter`) + HTTPS weather + defensive network monitoring
- Optional PyInstaller only when packaging
