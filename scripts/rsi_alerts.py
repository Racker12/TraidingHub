import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

RSI_PERIOD = 14
LOW_LEVEL = 30
HIGH_LEVEL = 70
STATE_FILE = Path("rsi_alert_state.json")
SEND_INITIAL_ALERTS = os.getenv("SEND_INITIAL_ALERTS", "false").lower() == "true"

# Alle Assets aus der Seasonality-App. Die Ticker sind Yahoo-Finance-Symbole.
# Falls ein Asset bei dir über einen anderen Markt laufen soll, hier einfach ticker ändern.
ASSETS = [
    {"key": "ABEA", "name": "Alphabet A", "ticker": "GOOGL"},
    {"key": "AMZ", "name": "Amazon", "ticker": "AMZN"},
    {"key": "APC", "name": "Apple", "ticker": "AAPL"},
    {"key": "BTC", "name": "Bitcoin", "ticker": "BTC-USD"},
    {"key": "BYD", "name": "BYD", "ticker": "1211.HK"},
    {"key": "ETH", "name": "Ethereum", "ticker": "ETH-USD"},
    {"key": "EURUSD", "name": "Euro / US-Dollar", "ticker": "EURUSD=X"},
    {"key": "GBPUSD", "name": "Britisches Pfund / US-Dollar", "ticker": "GBPUSD=X"},
    {"key": "MSF", "name": "Microsoft", "ticker": "MSFT"},
    {"key": "NASDAQ", "name": "Nasdaq 100", "ticker": "NQ=F"},
    {"key": "NVD", "name": "Nvidia", "ticker": "NVDA"},
    {"key": "PL", "name": "Palantir", "ticker": "PLTR"},
    {"key": "RheinmetallAG", "name": "Rheinmetall AG", "ticker": "RHM.DE"},
    {"key": "SI", "name": "Silber", "ticker": "SI=F"},
    {"key": "SOL", "name": "Solana", "ticker": "SOL-USD"},
    {"key": "Tesla", "name": "Tesla", "ticker": "TSLA"},
    {"key": "USDJPY", "name": "US-Dollar / Yen", "ticker": "JPY=X"},
    {"key": "VWCE", "name": "Vanguard FTSE All-World", "ticker": "VWCE.DE"},
    {"key": "XAU", "name": "Gold", "ticker": "GC=F"},
]

TIMEFRAMES = ["4H", "1D"]


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def rsi(series: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def download_close(ticker: str, timeframe: str) -> pd.Series:
    if timeframe == "1D":
        data = yf.download(ticker, period="500d", interval="1d", progress=False, auto_adjust=True, threads=False)
        close = data["Close"]
    else:
        data = yf.download(ticker, period="90d", interval="1h", progress=False, auto_adjust=True, threads=False)
        close = data["Close"].resample("4h").last().dropna()

    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = pd.to_numeric(close, errors="coerce").dropna()
    return close


def zone(value: float) -> str:
    if value < LOW_LEVEL:
        return "oversold"
    if value > HIGH_LEVEL:
        return "overbought"
    return "neutral"


def zone_text(z: str) -> str:
    if z == "oversold":
        return f"unter {LOW_LEVEL}"
    if z == "overbought":
        return f"über {HIGH_LEVEL}"
    return "neutral"


def send_telegram(message: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN oder TELEGRAM_CHAT_ID fehlt in GitHub Secrets.")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(url, data={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=20)
    response.raise_for_status()


def build_message(asset: dict, timeframe: str, value: float, price: float, z: str) -> str:
    emoji = "🟢" if z == "oversold" else "🔴"
    direction_hint = "möglicher überverkaufter Bereich" if z == "oversold" else "möglicher überkaufter Bereich"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"{emoji} <b>RSI Alert</b>\n"
        f"Asset: <b>{asset['name']} ({asset['key']})</b>\n"
        f"Chart: <b>{timeframe}</b>\n"
        f"RSI: <b>{value:.2f}</b> ({zone_text(z)})\n"
        f"Preis: <b>{price:.4f}</b>\n"
        f"Status: {direction_hint}\n"
        f"Zeit: {now}\n\n"
        f"Keine Finanzberatung. Bitte Trend, News, Volumen und Risk Management prüfen."
    )


def main() -> None:
    state = load_state()
    alerts_sent = 0
    errors = []
    checked = 0

    for asset in ASSETS:
        for timeframe in TIMEFRAMES:
            state_key = f"{asset['key']}|{timeframe}"
            try:
                close = download_close(asset["ticker"], timeframe)
                if len(close) < RSI_PERIOD + 5:
                    raise RuntimeError("Nicht genug Kursdaten empfangen.")

                current_rsi = float(rsi(close).dropna().iloc[-1])
                current_price = float(close.iloc[-1])
                current_zone = zone(current_rsi)
                previous_zone = state.get(state_key, {}).get("zone")

                should_alert = current_zone in {"oversold", "overbought"} and (
                    previous_zone not in {"oversold", "overbought"} if previous_zone is not None else SEND_INITIAL_ALERTS
                )

                if should_alert:
                    send_telegram(build_message(asset, timeframe, current_rsi, current_price, current_zone))
                    alerts_sent += 1

                state[state_key] = {
                    "zone": current_zone,
                    "rsi": round(current_rsi, 2),
                    "price": round(current_price, 6),
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "ticker": asset["ticker"],
                }
                checked += 1
                print(f"OK {asset['key']} {timeframe}: RSI {current_rsi:.2f}, zone {current_zone}")

            except Exception as exc:
                msg = f"{asset['key']} {timeframe} ({asset['ticker']}): {exc}"
                errors.append(msg)
                print("ERROR", msg)
                state.setdefault(state_key, {})["last_error"] = msg
                state[state_key]["checked_at"] = datetime.now(timezone.utc).isoformat()

    save_state(state)
    print(f"Checked: {checked}, alerts sent: {alerts_sent}, errors: {len(errors)}")
    if errors:
        print("Einige Assets konnten nicht geladen werden. Prüfe ggf. die Yahoo-Ticker in scripts/rsi_alerts.py.")


if __name__ == "__main__":
    main()
