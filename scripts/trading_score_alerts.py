import os
import json
import math
import time
import requests
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

STATE_FILE = Path("trading_score_state.json")
DATA_DIR = Path("Data")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

MIN_SCORE = int(os.getenv("TRADING_SCORE_MIN", "70"))
STRONG_SCORE = int(os.getenv("TRADING_SCORE_STRONG", "80"))
RESET_BELOW = int(os.getenv("TRADING_SCORE_RESET_BELOW", "60"))
COOLDOWN_HOURS = int(os.getenv("TRADING_SCORE_COOLDOWN_HOURS", "6"))
SEND_INITIAL_ALERTS = os.getenv("SEND_INITIAL_SCORE_ALERTS", "false").lower() == "true"

TIMEZONE = ZoneInfo("Europe/Berlin")

TIMEFRAMES = ["1H", "4H", "1D"]

ASSETS = [
    {"key": "ABEA", "name": "iShares AEX ETF", "ticker": "ABEA.AS", "group": "europe", "periods": [5, 10, 15]},
    {"key": "AMZ", "name": "Amazon", "ticker": "AMZN", "group": "us", "periods": [5, 10]},
    {"key": "APC", "name": "Apple", "ticker": "AAPL", "group": "us", "periods": [5, 10, 15]},
    {"key": "BTC", "name": "Bitcoin", "ticker": "BTC-USD", "group": "crypto", "periods": [5, 10, 15]},
    {"key": "BYD", "name": "BYD", "ticker": "1211.HK", "group": "asia", "periods": [5, 7]},
    {"key": "ETH", "name": "Ethereum", "ticker": "ETH-USD", "group": "crypto", "periods": [5, 10]},
    {"key": "EURUSD", "name": "Euro / US-Dollar", "ticker": "EURUSD=X", "group": "forex_major", "periods": [5, 10]},
    {"key": "GBPUSD", "name": "Britisches Pfund / US-Dollar", "ticker": "GBPUSD=X", "group": "forex_major", "periods": [5, 10]},
    {"key": "MSF", "name": "Microsoft", "ticker": "MSFT", "group": "us", "periods": [5, 10, 15]},
    {"key": "NASDAQ", "name": "Nasdaq 100", "ticker": "NQ=F", "group": "us_index", "periods": [5, 10, 15]},
    {"key": "NVD", "name": "Nvidia", "ticker": "NVDA", "group": "us", "periods": [5, 8]},
    {"key": "PL", "name": "Platin", "ticker": "PL=F", "group": "metals", "periods": [5, 10, 15, 25]},
    {"key": "RheinmetallAG", "name": "Rheinmetall AG", "ticker": "RHM.DE", "group": "europe", "periods": [5, 10]},
    {"key": "SI", "name": "Silber", "ticker": "SI=F", "group": "metals", "periods": [5, 10, 15, 25]},
    {"key": "SOL", "name": "Solana", "ticker": "SOL-USD", "group": "crypto", "periods": [5]},
    {"key": "Tesla", "name": "Tesla", "ticker": "TSLA", "group": "us", "periods": [5, 10]},
    {"key": "USDJPY", "name": "US-Dollar / Japanischer Yen", "ticker": "JPY=X", "group": "usd_jpy", "periods": [5, 10]},
    {"key": "VWCE", "name": "Vanguard FTSE All-World ETF", "ticker": "VWCE.DE", "group": "europe", "periods": [5]},
    {"key": "XAU", "name": "Gold", "ticker": "GC=F", "group": "metals", "periods": [5, 10, 15, 25]},
]

SESSIONS = [
    {"name": "Sydney", "open": 23.0, "close": 8.0},
    {"name": "Asia", "open": 2.0, "close": 11.0},
    {"name": "London", "open": 9.0, "close": 18.0},
    {"name": "New York", "open": 13.5, "close": 20.0},
]

SESSION_GROUPS = {
    "crypto": ["24/7"],
    "forex_major": ["London", "New York"],
    "usd_jpy": ["Asia", "New York"],
    "metals": ["London", "New York"],
    "us": ["New York"],
    "us_index": ["New York"],
    "europe": ["London"],
    "asia": ["Asia"],
}


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram secrets fehlen.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    response = requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=20,
    )
    print("Telegram:", response.status_code, response.text[:300])


def flatten_yfinance_columns(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
    return df


def download_data(ticker, timeframe):
    if timeframe == "1D":
        data = yf.download(ticker, period="600d", interval="1d", progress=False, auto_adjust=False)
    else:
        data = yf.download(ticker, period="730d", interval="1h", progress=False, auto_adjust=False)

    if data is None or data.empty:
        return pd.DataFrame()

    data = flatten_yfinance_columns(data)

    needed = ["Open", "High", "Low", "Close"]
    for col in needed:
        if col not in data.columns:
            return pd.DataFrame()

    if "Volume" not in data.columns:
        data["Volume"] = 0

    data = data[["Open", "High", "Low", "Close", "Volume"]].dropna()

    if timeframe == "2H":
        data = data.resample("2h").agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum"
        }).dropna()

    if timeframe == "4H":
        data = data.resample("4h").agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum"
        }).dropna()

    # Wichtig: letzte Kerze wird ignoriert, weil sie noch offen sein kann.
    # Dadurch arbeitet der Bot nur mit geschlossenen Kerzen.
    if len(data) > 250:
        data = data.iloc[:-1]

    return data.dropna()


def ema(series, length):
    return series.ewm(span=length, adjust=False).mean()


def rsi(series, length=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    value = 100 - (100 / (1 + rs))
    return value.fillna(50)


def macd(series):
    fast = ema(series, 12)
    slow = ema(series, 26)
    macd_line = fast - slow
    signal = ema(macd_line, 9)
    hist = macd_line - signal
    return macd_line, signal, hist


def atr(df, length=14):
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    return tr.ewm(alpha=1 / length, adjust=False).mean()


def adx_di(df, length=14):
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = atr(df, length)
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / length, adjust=False).mean() / tr
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / length, adjust=False).mean() / tr

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_value = dx.ewm(alpha=1 / length, adjust=False).mean()

    return adx_value.fillna(0), plus_di.fillna(0), minus_di.fillna(0)


def bollinger(series, length=20, std=2):
    mid = series.rolling(length).mean()
    dev = series.rolling(length).std()
    upper = mid + std * dev
    lower = mid - std * dev
    return upper, mid, lower


def stochastic_rsi(rsi_series, length=14):
    lowest = rsi_series.rolling(length).min()
    highest = rsi_series.rolling(length).max()
    stoch = 100 * (rsi_series - lowest) / (highest - lowest).replace(0, np.nan)
    k = stoch.rolling(3).mean()
    d = k.rolling(3).mean()
    return k.fillna(50), d.fillna(50)


def session_is_open(session, now):
    current = now.hour + now.minute / 60
    open_time = session["open"]
    close_time = session["close"]

    if open_time < close_time:
        return open_time <= current < close_time

    return current >= open_time or current < close_time


def get_open_sessions():
    now = datetime.now(TIMEZONE)
    open_names = []
    for session in SESSIONS:
        if session_is_open(session, now):
            open_names.append(session["name"])
    return open_names


def seasonality_score(asset_key, periods):
    now = datetime.now(TIMEZONE)
    month_index = now.month - 1
    weekday_index = now.weekday()

    file_path = None
    for period in sorted(periods, reverse=True):
        candidate = DATA_DIR / f"{asset_key}{period}.txt"
        if candidate.exists():
            file_path = candidate
            break

    if not file_path:
        return 0, 0, "keine Seasonality-Datei gefunden"

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        monthly = data.get("monthlyChartData", {}).get("values", [])
        weekday = data.get("weekdayChartData", {}).get("values", [])

        month_value = float(monthly[month_index]) if len(monthly) > month_index else 0
        weekday_value = float(weekday[weekday_index]) if len(weekday) > weekday_index else 0

        long_points = 0
        short_points = 0

        if month_value > 3:
            long_points += 5
        elif month_value > 1:
            long_points += 3
        elif month_value > 0:
            long_points += 1

        if month_value < -3:
            short_points += 5
        elif month_value < -1:
            short_points += 3
        elif month_value < 0:
            short_points += 1

        if weekday_value > 0.1:
            long_points += 3
        elif weekday_value > 0:
            long_points += 1

        if weekday_value < -0.1:
            short_points += 3
        elif weekday_value < 0:
            short_points += 1

        long_points = min(long_points, 8)
        short_points = min(short_points, 8)

        reason = f"Monat {month_value:+.2f}%, Wochentag {weekday_value:+.2f}%"
        return long_points, short_points, reason

    except Exception as exc:
        return 0, 0, f"Seasonality Fehler: {exc}"


def add_reason(reasons, points, text):
    if points > 0:
        reasons.append(f"+{points} {text}")


def calculate_score(df, asset):
    if len(df) < 220:
        return None

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    current_close = float(close.iloc[-1])
    previous_close = float(close.iloc[-2])
    current_open = float(df["Open"].iloc[-1])

    candle_time = str(df.index[-1])

    ema50 = ema(close, 50)
    ema200 = ema(close, 200)
    rsi_values = rsi(close)
    macd_line, macd_signal, macd_hist = macd(close)
    adx_value, plus_di, minus_di = adx_di(df)
    bb_upper, bb_mid, bb_lower = bollinger(close)
    stoch_k, stoch_d = stochastic_rsi(rsi_values)
    atr_values = atr(df)

    current_rsi = float(rsi_values.iloc[-1])
    previous_rsi = float(rsi_values.iloc[-2])

    long_score = 0
    short_score = 0
    long_reasons = []
    short_reasons = []

    # 1. EMA Trend: 20 Punkte
    points = 0
    if current_close > float(ema200.iloc[-1]):
        points += 8
    if current_close > float(ema50.iloc[-1]):
        points += 5
    if float(ema50.iloc[-1]) > float(ema200.iloc[-1]):
        points += 7
    long_score += points
    add_reason(long_reasons, points, "EMA-Trend bullish")

    points = 0
    if current_close < float(ema200.iloc[-1]):
        points += 8
    if current_close < float(ema50.iloc[-1]):
        points += 5
    if float(ema50.iloc[-1]) < float(ema200.iloc[-1]):
        points += 7
    short_score += points
    add_reason(short_reasons, points, "EMA-Trend bearish")

    # 2. RSI: 15 Punkte
    points = 0
    if previous_rsi < 30 <= current_rsi:
        points += 8
    elif current_rsi < 30:
        points += 4
    if current_rsi > previous_rsi:
        points += 3
    if 30 <= current_rsi <= 55:
        points += 4
    points = min(points, 15)
    long_score += points
    add_reason(long_reasons, points, f"RSI Long-Struktur ({current_rsi:.1f})")

    points = 0
    if previous_rsi > 70 >= current_rsi:
        points += 8
    elif current_rsi > 70:
        points += 4
    if current_rsi < previous_rsi:
        points += 3
    if 45 <= current_rsi <= 70:
        points += 4
    points = min(points, 15)
    short_score += points
    add_reason(short_reasons, points, f"RSI Short-Struktur ({current_rsi:.1f})")

    # 3. MACD: 10 Punkte
    points = 0
    if float(macd_line.iloc[-1]) > float(macd_signal.iloc[-1]):
        points += 5
    if float(macd_hist.iloc[-1]) > float(macd_hist.iloc[-2]):
        points += 5
    long_score += points
    add_reason(long_reasons, points, "MACD bullish")

    points = 0
    if float(macd_line.iloc[-1]) < float(macd_signal.iloc[-1]):
        points += 5
    if float(macd_hist.iloc[-1]) < float(macd_hist.iloc[-2]):
        points += 5
    short_score += points
    add_reason(short_reasons, points, "MACD bearish")

    # 4. ADX / DI: 10 Punkte
    current_adx = float(adx_value.iloc[-1])
    current_plus_di = float(plus_di.iloc[-1])
    current_minus_di = float(minus_di.iloc[-1])

    points = 0
    if current_plus_di > current_minus_di:
        points += 6
    if current_adx > 25:
        points += 4
    elif current_adx > 20:
        points += 2
    points = min(points, 10)
    long_score += points
    add_reason(long_reasons, points, f"ADX/DI bullish (ADX {current_adx:.1f})")

    points = 0
    if current_minus_di > current_plus_di:
        points += 6
    if current_adx > 25:
        points += 4
    elif current_adx > 20:
        points += 2
    points = min(points, 10)
    short_score += points
    add_reason(short_reasons, points, f"ADX/DI bearish (ADX {current_adx:.1f})")

    # 5. Bollinger Bands: 8 Punkte
    points = 0
    if previous_close < float(bb_lower.iloc[-2]) and current_close > float(bb_lower.iloc[-1]):
        points += 6
    elif current_close <= float(bb_lower.iloc[-1]) * 1.01:
        points += 3
    if current_close > previous_close:
        points += 2
    points = min(points, 8)
    long_score += points
    add_reason(long_reasons, points, "Bollinger Long-Reaktion")

    points = 0
    if previous_close > float(bb_upper.iloc[-2]) and current_close < float(bb_upper.iloc[-1]):
        points += 6
    elif current_close >= float(bb_upper.iloc[-1]) * 0.99:
        points += 3
    if current_close < previous_close:
        points += 2
    points = min(points, 8)
    short_score += points
    add_reason(short_reasons, points, "Bollinger Short-Reaktion")

    # 6. Stoch RSI: 7 Punkte
    k_now = float(stoch_k.iloc[-1])
    d_now = float(stoch_d.iloc[-1])
    k_prev = float(stoch_k.iloc[-2])
    d_prev = float(stoch_d.iloc[-2])

    points = 0
    if k_prev < d_prev and k_now > d_now and k_now < 30:
        points += 7
    elif k_now < 20:
        points += 4
    long_score += points
    add_reason(long_reasons, points, f"Stoch RSI Long ({k_now:.1f})")

    points = 0
    if k_prev > d_prev and k_now < d_now and k_now > 70:
        points += 7
    elif k_now > 80:
        points += 4
    short_score += points
    add_reason(short_reasons, points, f"Stoch RSI Short ({k_now:.1f})")

    # 7. Support / Resistance: 10 Punkte
    recent_lows = low.iloc[-60:-1]
    recent_highs = high.iloc[-60:-1]

    support = float(recent_lows.min())
    resistance = float(recent_highs.max())

    distance_support = abs(current_close - support) / current_close * 100
    distance_resistance = abs(resistance - current_close) / current_close * 100

    points = 0
    if distance_support <= 1.5 and current_close > previous_close:
        points += 10
    elif distance_support <= 3:
        points += 5
    long_score += points
    add_reason(long_reasons, points, f"nahe Support ({distance_support:.2f}%)")

    points = 0
    if distance_resistance <= 1.5 and current_close < previous_close:
        points += 10
    elif distance_resistance <= 3:
        points += 5
    short_score += points
    add_reason(short_reasons, points, f"nahe Resistance ({distance_resistance:.2f}%)")

    # 8. Seasonality: 8 Punkte
    season_long, season_short, season_reason = seasonality_score(asset["key"], asset["periods"])
    long_score += season_long
    short_score += season_short
    add_reason(long_reasons, season_long, f"Seasonality positiv: {season_reason}")
    add_reason(short_reasons, season_short, f"Seasonality negativ: {season_reason}")

    # 9. Session: 5 Punkte
    open_sessions = get_open_sessions()
    wanted_sessions = SESSION_GROUPS.get(asset["group"], [])

    session_points = 0
    if "24/7" in wanted_sessions:
        session_points = 5
    elif any(session in open_sessions for session in wanted_sessions):
        session_points = 5

    long_score += session_points
    short_score += session_points
    add_reason(long_reasons, session_points, f"passende Session offen: {', '.join(open_sessions) or 'keine'}")
    add_reason(short_reasons, session_points, f"passende Session offen: {', '.join(open_sessions) or 'keine'}")

    # 10. ATR / Volatilität: 5 Punkte
    current_atr = float(atr_values.iloc[-1])
    atr_percent = current_atr / current_close * 100 if current_close else 0

    points = 0
    if 0.4 <= atr_percent <= 8:
        points = 5
    elif 0.2 <= atr_percent < 0.4:
        points = 2

    long_score += points
    short_score += points
    add_reason(long_reasons, points, f"ATR gesund ({atr_percent:.2f}%)")
    add_reason(short_reasons, points, f"ATR gesund ({atr_percent:.2f}%)")

    # 11. Volumen / Candle: 2 Punkte
    avg_volume = float(volume.iloc[-30:].mean()) if len(volume) >= 30 else 0
    current_volume = float(volume.iloc[-1])

    points = 0
    if avg_volume > 0 and current_volume > avg_volume * 1.2 and current_close > current_open:
        points = 2
    long_score += points
    add_reason(long_reasons, points, "bullische Kerze mit erhöhtem Volumen")

    points = 0
    if avg_volume > 0 and current_volume > avg_volume * 1.2 and current_close < current_open:
        points = 2
    short_score += points
    add_reason(short_reasons, points, "bearishe Kerze mit erhöhtem Volumen")

    long_score = int(min(round(long_score), 100))
    short_score = int(min(round(short_score), 100))

    return {
        "candle_time": candle_time,
        "close": current_close,
        "rsi": current_rsi,
        "adx": current_adx,
        "atr_percent": atr_percent,
        "long_score": long_score,
        "short_score": short_score,
        "long_reasons": long_reasons,
        "short_reasons": short_reasons,
    }


def should_send_alert(state, state_key, score, candle_time):
    previous = state.get(state_key)

    if previous and previous.get("candle_time") == candle_time:
        return False

    if not previous:
        state[state_key] = {
            "active": score >= MIN_SCORE,
            "last_score": score,
            "candle_time": candle_time,
            "last_alert_at": None,
        }
        return SEND_INITIAL_ALERTS and score >= MIN_SCORE

    last_alert_at = previous.get("last_alert_at")
    active = previous.get("active", False)
    last_score = int(previous.get("last_score", 0))

    if score < RESET_BELOW:
        previous["active"] = False

    cooldown_ok = True
    if last_alert_at:
        try:
            last_dt = datetime.fromisoformat(last_alert_at)
            cooldown_ok = datetime.now(timezone.utc) - last_dt > timedelta(hours=COOLDOWN_HOURS)
        except Exception:
            cooldown_ok = True

    crossed_new = score >= MIN_SCORE and (not active or last_score < RESET_BELOW)

    previous["last_score"] = score
    previous["candle_time"] = candle_time

    return crossed_new and cooldown_ok


def mark_alert_sent(state, state_key, score, candle_time):
    state[state_key] = {
        "active": True,
        "last_score": score,
        "candle_time": candle_time,
        "last_alert_at": datetime.now(timezone.utc).isoformat(),
    }


def build_message(asset, timeframe, bias, score, result):
    strength = "🔥 STRONG" if score >= STRONG_SCORE else "🚨 ALERT"
    reasons = result["long_reasons"] if bias == "LONG" else result["short_reasons"]

    reason_lines = "\n".join([f"✅ {r}" for r in reasons[:8]])

    return f"""<b>{strength} Trading Score</b>

<b>Asset:</b> {asset["name"]} ({asset["key"]})
<b>Timeframe:</b> {timeframe}
<b>Bias:</b> {bias}
<b>Score:</b> {score}/100

<b>Kurs:</b> {result["close"]:.4f}
<b>RSI:</b> {result["rsi"]:.1f}
<b>ADX:</b> {result["adx"]:.1f}
<b>ATR:</b> {result["atr_percent"]:.2f}%

<b>Kerze:</b> geschlossen
<b>Candle:</b> {result["candle_time"]}

<b>Gründe:</b>
{reason_lines}

Hinweis: Kein automatischer Kauf/Verkauf. Setup mit Entry, SL und Risiko prüfen."""


def main():
    state = load_state()

    for asset in ASSETS:
        for timeframe in TIMEFRAMES:
            print(f"Prüfe {asset['key']} {timeframe}...")

            try:
                df = download_data(asset["ticker"], timeframe)

                if df.empty or len(df) < 220:
                    print(f"Nicht genug Daten für {asset['key']} {timeframe}")
                    continue

                result = calculate_score(df, asset)

                if not result:
                    continue

                for bias in ["LONG", "SHORT"]:
                    score = result["long_score"] if bias == "LONG" else result["short_score"]
                    state_key = f"{asset['key']}:{timeframe}:{bias}"

                    print(asset["key"], timeframe, bias, score)

                    if should_send_alert(state, state_key, score, result["candle_time"]):
                        message = build_message(asset, timeframe, bias, score, result)
                        send_telegram(message)
                        mark_alert_sent(state, state_key, score, result["candle_time"])

                time.sleep(0.4)

            except Exception as exc:
                print(f"Fehler bei {asset['key']} {timeframe}: {exc}")

    save_state(state)


if __name__ == "__main__":
    main()
