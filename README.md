# Assist

A light daily desk for the places you work across — local time and weather, with quick add/remove.

## Run locally

Serve the project root with any static server:

```bash
python3 -m http.server 4173 --bind 127.0.0.1
```

Open `http://127.0.0.1:4173`.

## Notes

- Places are stored in your browser (`localStorage`)
- Weather data comes from [Open-Meteo](https://open-meteo.com/) (no API key)
- Designed mobile-first and keeps the UI intentionally light
