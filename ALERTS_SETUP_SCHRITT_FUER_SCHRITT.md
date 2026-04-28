# Telegram Alerts: Schritt für Schritt nach dem Entpacken

Diese Version sendet automatisch Telegram-Nachrichten für:

1. RSI-Alerts für alle Assets aus der Seasonality-App
   - 4H RSI unter 30
   - 4H RSI über 70
   - 1D RSI unter 30
   - 1D RSI über 70
2. Session-Alerts
   - Nachricht, wenn Sydney, Asia, London oder New York öffnet
   - Nachricht, wenn Sydney, Asia, London oder New York schließt
   - Beim manuellen Testlauf wird einmal der aktuelle Session-Status gesendet

## 1. ZIP entpacken

Entpacke die ZIP-Datei auf deinem PC.

Danach hast du ungefähr diese Struktur:

```text
index.html
style.css
script.js
Data/
.github/workflows/rsi-telegram-alerts.yml
scripts/rsi_alerts.py
scripts/session_alerts.py
requirements.txt
rsi_alert_state.json
session_alert_state.json
```

## 2. Dateien in GitHub hochladen

Öffne dein GitHub Repository.

Lade ALLES hoch, besonders diese Ordner:

```text
.github
scripts
Data
```

Wichtig: `.github` beginnt mit einem Punkt. Der Ordner muss exakt so heißen.

## 3. Prüfen, ob GitHub Actions aktiv ist

Gehe in deinem Repo oben auf:

```text
Actions
```

Falls GitHub fragt, ob Workflows aktiviert werden sollen, klicke auf Aktivieren.

## 4. Telegram Secrets eintragen

Gehe in deinem Repo auf:

```text
Settings → Secrets and variables → Actions → New repository secret
```

Erstelle Secret 1:

```text
Name: TELEGRAM_BOT_TOKEN
Secret: dein Bot Token von BotFather
```

Erstelle Secret 2:

```text
Name: TELEGRAM_CHAT_ID
Secret: deine Telegram Chat ID
```

## 5. Erster Test

Gehe auf:

```text
Actions → RSI and Session Telegram Alerts → Run workflow
```

Dann sollte Telegram mindestens eine Nachricht mit dem aktuellen Session-Status senden.

RSI-Alerts kommen nur, wenn wirklich ein Asset neu unter RSI 30 oder neu über RSI 70 kommt. Beim ersten Lauf werden alte RSI-Zustände bewusst nicht gespammt.

## 6. Automatik

Danach läuft der Workflow automatisch alle 15 Minuten.

- Session-Alerts werden geschickt, wenn eine Session seit dem letzten Lauf geöffnet oder geschlossen hat.
- RSI-Alerts werden geschickt, wenn ein Asset neu in die Zone unter 30 oder über 70 kommt.
- Wiederholungen werden durch die State-Dateien verhindert.

## 7. Ticker ändern

Wenn ein Asset falsche Kursdaten liefert, öffne:

```text
scripts/rsi_alerts.py
```

Dort findest du die Liste `ASSETS`.

Beispiel:

```python
{"key": "BTC", "name": "Bitcoin", "ticker": "BTC-USD"}
```

Der `ticker` ist der Yahoo-Finance-Ticker.

## 8. Sessionzeiten ändern

Öffne:

```text
scripts/session_alerts.py
```

Dort steht:

```python
SESSIONS = [
    {"name": "Sydney", "open": 23.0, "close": 8.0},
    {"name": "Asia", "open": 2.0, "close": 11.0},
    {"name": "London", "open": 9.0, "close": 18.0},
    {"name": "New York", "open": 13.5, "close": 20.0},
]
```

`13.5` bedeutet 13:30.

Standard-Zeitzone ist:

```text
Europe/Berlin
```

## 9. Häufige Fehler

### Keine Nachricht kommt an

Prüfe:

- Hast du dem Bot in Telegram einmal `/start` geschrieben?
- Ist `TELEGRAM_BOT_TOKEN` richtig geschrieben?
- Ist `TELEGRAM_CHAT_ID` richtig geschrieben?
- Sind die Secrets exakt so benannt?

### Workflow erscheint nicht

Prüfe:

- Ist die Datei wirklich hier?

```text
.github/workflows/rsi-telegram-alerts.yml
```

- Ist der Ordner `.github` wirklich mit Punkt am Anfang?

### RSI-Daten fehlen

Manche Yahoo-Finance-Ticker können kurzzeitig keine Daten liefern. Der Workflow läuft beim nächsten Intervall erneut.

## Sicherheit

Der Telegram Bot Token liegt nicht im Code, sondern in GitHub Secrets. Lade den Token niemals direkt in `script.js`, `index.html` oder eine öffentliche Datei hoch.
