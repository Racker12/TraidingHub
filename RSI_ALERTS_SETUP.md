# Automatische RSI Telegram Alerts

Diese Version enthält einen fertigen GitHub-Actions-Workflow, der automatisch alle Assets aus der Seasonality-App prüft.

## Was wird geprüft?

Für jedes Asset werden zwei Timeframes geprüft:

- 4H RSI
- 1D RSI

Ein Telegram Alert wird gesendet, wenn der RSI neu in einen dieser Bereiche kommt:

- RSI unter 30
- RSI über 70

Damit du nicht jede Stunde dieselbe Nachricht bekommst, speichert der Workflow den letzten Status in `rsi_alert_state.json`. Erst wenn ein Asset aus neutral wieder unter 30 oder über 70 kommt, gibt es wieder eine Nachricht.

## Dateien im Projekt

```text
index.html
style.css
script.js
requirements.txt
rsi_alert_state.json
scripts/rsi_alerts.py
.github/workflows/rsi-telegram-alerts.yml
Data/
```

Dein `Data`-Ordner bleibt wie bisher für die Seasonality-App. Die RSI-Alerts laden Kursdaten über Yahoo-Finance-Ticker in `scripts/rsi_alerts.py`.

## GitHub Secrets eintragen

Gehe in deinem GitHub Repository auf:

```text
Settings → Secrets and variables → Actions → New repository secret
```

Lege diese zwei Secrets an:

```text
TELEGRAM_BOT_TOKEN
```

und

```text
TELEGRAM_CHAT_ID
```

## Workflow starten

Nach dem Hochladen findest du in GitHub:

```text
Actions → RSI Telegram Alerts
```

Dort kannst du mit **Run workflow** einmal manuell testen.

Danach läuft der Workflow automatisch stündlich.

## Asset-Ticker ändern

Wenn ein Asset nicht lädt, öffne:

```text
scripts/rsi_alerts.py
```

Dort gibt es die Liste `ASSETS`. Beispiel:

```python
{"key": "BTC", "name": "Bitcoin", "ticker": "BTC-USD"}
```

Du kannst nur den `ticker` ändern, wenn dein Markt anders heißen soll.

## Wichtig

- Beim ersten Lauf werden standardmäßig keine bestehenden RSI-Zustände als Alert gesendet. Das verhindert Spam.
- Danach bekommst du Alerts nur bei neuen Wechseln unter 30 oder über 70.
- Wenn du beim ersten Lauf sofort alle aktuellen RSI-Extremwerte gemeldet haben willst, ändere in `.github/workflows/rsi-telegram-alerts.yml`:

```yaml
SEND_INITIAL_ALERTS: "true"
```

Danach am besten wieder auf `false` stellen.
