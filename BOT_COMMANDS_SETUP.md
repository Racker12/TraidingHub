# Telegram Bot Commands

Diese Version ergänzt deinen bestehenden Telegram-Bot um Befehle.

## Neue Datei

- `scripts/telegram_commands.py`
- `telegram_command_state.json`
- geänderte `.github/workflows/rsi-telegram-alerts.yml`

## Befehle in Telegram

- `/info` — Übersicht über alle Befehle und Assets
- `/assets` — Asset-Liste
- `/sessions` — aktuelle Trading Sessions
- `/giveBTC` — Bitcoin Kursdaten
- `/give BTC` — gleiche Funktion mit Leerzeichen
- `/giveXAU`, `/giveTesla`, `/giveEURUSD`, `/giveSI` usw.

## Was /give sendet

- aktueller Kurs
- Tageshoch
- Tagestief
- Tages-Open
- Veränderung ggü. Vortag
- Volumen, falls verfügbar
- RSI 1D
- RSI 4H

## Wichtig

GitHub Actions prüft neue Telegram-Befehle nach Zeitplan. In dieser Version ist es alle 5 Minuten:

```yaml
cron: "*/5 * * * *"
```

Das heißt: Eine Antwort auf `/giveBTC` kommt nicht immer sofort, sondern spätestens beim nächsten Workflow-Lauf.

Der Bot antwortet standardmäßig nur auf die Chat-ID aus deinem GitHub Secret `TELEGRAM_CHAT_ID`.
