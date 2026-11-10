# Assist

Light Windows desktop app for daily work across places — local time, weather, and a network guard that watches for strange or dangerous traffic.

## Easiest way to run (Windows `.exe`)

### Option A — download the built exe (recommended)

1. Open the GitHub Actions run for this branch: **Build Assist.exe**
2. Download the **Assist-windows** artifact
3. Unzip and double-click **`Assist.exe`**

If SmartScreen appears: **More info → Run anyway**.

### Option B — build the exe on your PC

1. Install [Python 3.10+](https://www.python.org/downloads/) (check **Add python.exe to PATH**)
2. Double-click **`Build Assist.exe.bat`**
3. When it finishes, double-click **`Release\Assist.exe`**

That creates a single-file windowed app — no console window, no Python needed to run it afterward.

## Features

- Live local time for each saved place
- Current weather (Open-Meteo, no API key)
- Add / remove places
- Network guard alerts for suspicious listeners, watched ports, and scan-like bursts
- Compact small window (~380×520)
- Data saved under `%USERPROFILE%\.assist\`

## Run from source

```bat
pip install -r requirements.txt
python main.py
```

Or double-click `scripts\run-assist.bat`.

## Network guard notes

- Default: light connection analysis (no admin)
- Packet capture on Windows needs Administrator + Npcap
- Use **Test** in the Guard row to verify notifications
