import html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf

RSI_PERIOD = 14
STATE_FILE = Path("telegram_command_state.json")
LOCAL_TIMEZONE = os.getenv("SESSION_TIMEZONE", "Europe/Berlin")
LOW_LEVEL = 30
HIGH_LEVEL = 70

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

ASSET_LOOKUP = {a["key"].upper(): a for a in ASSETS}
# Ein paar Aliasse, damit Befehle natürlicher funktionieren.
ALIASES = {
    "BITCOIN": "BTC", "BTCUSD": "BTC",
    "ETHEREUM": "ETH", "ETHUSD": "ETH",
    "GOLD": "XAU", "XAUUSD": "XAU",
    "SILBER": "SI", "SILVER": "SI", "XAG": "SI", "XAGUSD": "SI",
    "APPLE": "APC", "AAPL": "APC",
    "AMAZON": "AMZ", "AMZN": "AMZ",
    "MICROSOFT": "MSF", "MSFT": "MSF",
    "NVIDIA": "NVD", "NVDA": "NVD",
    "PALANTIR": "PL", "PLTR": "PL",
    "TESLA": "Tesla", "TSLA": "Tesla",
    "RHEINMETALL": "RheinmetallAG", "RHM": "RheinmetallAG",
}

SESSIONS = [
    {"name": "Sydney", "open": 23.0, "close": 8.0},
    {"name": "Asia", "open": 2.0, "close": 11.0},
    {"name": "London", "open": 9.0, "close": 18.0},
    {"name": "New York", "open": 13.5, "close": 20.0},
]


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def telegram_request(method: str, data: dict | None = None) -> dict:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN fehlt in GitHub Secrets.")
    url = f"https://api.telegram.org/bot{token}/{method}"
    response = requests.post(url, data=data or {}, timeout=25)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API Fehler: {payload}")
    return payload


def send_message(chat_id: int | str, text: str) -> None:
    # Telegram kann maximal ca. 4096 Zeichen pro Nachricht. Sicherheitshalber teilen.
    chunks = []
    remaining = text
    while len(remaining) > 3900:
        cut = remaining.rfind("\n", 0, 3900)
        if cut == -1:
            cut = 3900
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip()
    chunks.append(remaining)

    for chunk in chunks:
        telegram_request("sendMessage", {
            "chat_id": str(chat_id),
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        })


def allowed_chat(chat_id: int | str) -> bool:
    allow_all = os.getenv("ALLOW_ALL_COMMAND_CHATS", "false").lower() == "true"
    configured = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if allow_all:
        return True
    return configured and str(chat_id) == configured


def esc(value) -> str:
    return html.escape(str(value), quote=False)


def format_number(value: float | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    abs_value = abs(float(value))
    if abs_value >= 1000:
        return f"{float(value):,.2f}"
    if abs_value >= 10:
        return f"{float(value):.2f}"
    if abs_value >= 1:
        return f"{float(value):.4f}"
    return f"{float(value):.6f}"


def calc_rsi(series: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
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
    elif timeframe == "4H":
        data = yf.download(ticker, period="90d", interval="1h", progress=False, auto_adjust=True, threads=False)
        close = data["Close"].resample("4h").last().dropna()
    else:
        raise ValueError(f"Nicht unterstützter Timeframe: {timeframe}")

    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return pd.to_numeric(close, errors="coerce").dropna()


def rsi_value(ticker: str, timeframe: str) -> float | None:
    close = download_close(ticker, timeframe)
    values = calc_rsi(close).dropna()
    if values.empty:
        return None
    return float(values.iloc[-1])


def rsi_status(value: float | None) -> str:
    if value is None:
        return "n/a"
    if value < LOW_LEVEL:
        return "überverkauft"
    if value > HIGH_LEVEL:
        return "überkauft"
    return "neutral"


def resolve_asset(raw: str) -> dict | None:
    token = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    if not token:
        return None
    if token in ASSET_LOOKUP:
        return ASSET_LOOKUP[token]
    if token in ALIASES:
        return ASSET_LOOKUP.get(ALIASES[token].upper()) or next((a for a in ASSETS if a["key"] == ALIASES[token]), None)
    for asset in ASSETS:
        if asset["name"].upper().replace(" ", "") == token:
            return asset
    return None


def latest_market_info(asset: dict) -> dict:
    ticker = asset["ticker"]
    # 5 Tage Tagesdaten für Tageshoch/-tief und Veränderung.
    daily = yf.download(ticker, period="5d", interval="1d", progress=False, auto_adjust=False, threads=False)
    if daily.empty:
        raise RuntimeError("Keine Kursdaten empfangen.")
    last = daily.dropna(how="all").iloc[-1]
    prev_close = None
    if len(daily.dropna(how="all")) >= 2:
        prev_close = float(daily.dropna(how="all")["Close"].iloc[-2])

    def get_col(row, name):
        value = row[name]
        if isinstance(value, pd.Series):
            value = value.iloc[0]
        return float(value) if not pd.isna(value) else None

    current_price = get_col(last, "Close")
    day_open = get_col(last, "Open")
    day_high = get_col(last, "High")
    day_low = get_col(last, "Low")
    volume = get_col(last, "Volume") if "Volume" in daily.columns else None
    change_abs = current_price - prev_close if prev_close else None
    change_pct = (change_abs / prev_close * 100) if prev_close and prev_close != 0 else None

    rsi_1d = rsi_value(ticker, "1D")
    rsi_4h = rsi_value(ticker, "4H")

    return {
        "price": current_price,
        "open": day_open,
        "high": day_high,
        "low": day_low,
        "prev_close": prev_close,
        "change_abs": change_abs,
        "change_pct": change_pct,
        "volume": volume,
        "rsi_1d": rsi_1d,
        "rsi_4h": rsi_4h,
    }


def build_asset_message(asset: dict) -> str:
    info = latest_market_info(asset)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    change = "n/a"
    if info["change_abs"] is not None and info["change_pct"] is not None:
        sign = "+" if info["change_abs"] >= 0 else ""
        change = f"{sign}{format_number(info['change_abs'])} ({sign}{info['change_pct']:.2f}%)"

    rsi_1d_text = "n/a" if info["rsi_1d"] is None else f"{info['rsi_1d']:.2f} · {rsi_status(info['rsi_1d'])}"
    rsi_4h_text = "n/a" if info["rsi_4h"] is None else f"{info['rsi_4h']:.2f} · {rsi_status(info['rsi_4h'])}"
    volume_text = "n/a" if info["volume"] is None else f"{info['volume']:,.0f}"

    return (
        f"📊 <b>{esc(asset['name'])} ({esc(asset['key'])})</b>\n"
        f"Ticker: <code>{esc(asset['ticker'])}</code>\n"
        f"Zeit: {now}\n\n"
        f"Aktueller Kurs: <b>{format_number(info['price'])}</b>\n"
        f"Veränderung ggü. Vortag: <b>{esc(change)}</b>\n"
        f"Tageshoch: <b>{format_number(info['high'])}</b>\n"
        f"Tagestief: <b>{format_number(info['low'])}</b>\n"
        f"Tages-Open: <b>{format_number(info['open'])}</b>\n"
        f"Volumen: <b>{esc(volume_text)}</b>\n\n"
        f"RSI 1D: <b>{esc(rsi_1d_text)}</b>\n"
        f"RSI 4H: <b>{esc(rsi_4h_text)}</b>\n\n"
        f"Befehl: <code>/give{esc(asset['key'])}</code>\n"
        "Keine Finanzberatung. Datenquelle: Yahoo Finance/yfinance."
    )


def local_hour(now: datetime) -> float:
    return now.hour + now.minute / 60 + now.second / 3600


def is_open(session: dict, hour: float) -> bool:
    open_h = session["open"]
    close_h = session["close"]
    if open_h < close_h:
        return open_h <= hour < close_h
    return hour >= open_h or hour < close_h


def fmt_hour(value: float) -> str:
    hour = int(value)
    minute = int(round((value - hour) * 60))
    return f"{hour:02d}:{minute:02d}"


def build_session_message() -> str:
    tz = ZoneInfo(LOCAL_TIMEZONE)
    now = datetime.now(tz)
    hour = local_hour(now)
    lines = []
    open_names = []
    for session in SESSIONS:
        current = is_open(session, hour)
        if current:
            open_names.append(session["name"])
            lines.append(f"🟢 <b>{session['name']}</b>: offen bis {fmt_hour(session['close'])}")
        else:
            lines.append(f"⚪ <b>{session['name']}</b>: geschlossen, öffnet {fmt_hour(session['open'])}")
    active = ", ".join(open_names) if open_names else "keine Session offen"
    return (
        "🕒 <b>Trading Sessions</b>\n"
        f"Zeit: <b>{now.strftime('%Y-%m-%d %H:%M')}</b> ({LOCAL_TIMEZONE})\n"
        f"Aktiv: <b>{esc(active)}</b>\n\n"
        + "\n".join(lines)
    )


def build_info_message() -> str:
    asset_lines = [f"• <b>{esc(a['name'])}</b> — <code>{esc(a['key'])}</code> → <code>/give{esc(a['key'])}</code>" for a in ASSETS]
    return (
        "🤖 <b>Trading Bot Befehle</b>\n\n"
        "<b>Wichtige Befehle</b>\n"
        "• <code>/info</code> — Übersicht über Befehle und Assets\n"
        "• <code>/assets</code> — nur Asset-Liste anzeigen\n"
        "• <code>/sessions</code> — aktuelle Trading Sessions\n"
        "• <code>/giveBTC</code> — Kursdaten für Bitcoin\n"
        "• <code>/give BTC</code> — gleiche Funktion mit Leerzeichen\n"
        "• <code>/giveXAU</code>, <code>/giveTesla</code>, <code>/giveEURUSD</code> usw.\n\n"
        "<b>Was /give liefert</b>\n"
        "Aktueller Kurs, Veränderung, Tageshoch, Tagestief, Tages-Open, Volumen, RSI 1D und RSI 4H.\n\n"
        "<b>Assets</b>\n" + "\n".join(asset_lines)
    )


def build_assets_message() -> str:
    lines = [f"• <b>{esc(a['name'])}</b> ({esc(a['key'])}) → <code>/give{esc(a['key'])}</code>" for a in ASSETS]
    return "📋 <b>Assets</b>\n\n" + "\n".join(lines)


def parse_command(text: str) -> tuple[str, str | None]:
    text = text.strip()
    first = text.split()[0] if text.split() else ""
    # Entferne optionales @BotName bei Telegram-Befehlen.
    first_clean = first.split("@")[0]
    rest = text[len(first):].strip()
    lower = first_clean.lower()

    if lower in {"/start", "/help", "/info"}:
        return "info", None
    if lower in {"/assets", "/asset"}:
        return "assets", None
    if lower in {"/sessions", "/session", "/börsen", "/boersen"}:
        return "sessions", None
    if lower == "/give":
        return "give", rest
    if lower.startswith("/give") and len(first_clean) > len("/give"):
        return "give", first_clean[len("/give"):]
    if lower in {"/kurs", "/price"}:
        return "give", rest
    return "unknown", None


def handle_message(message: dict) -> str | None:
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = message.get("text", "")
    if not chat_id or not text.startswith("/"):
        return None

    if not allowed_chat(chat_id):
        send_message(chat_id, "⛔ Dieser Bot ist für diesen Chat nicht freigegeben.")
        return "blocked"

    command, arg = parse_command(text)
    if command == "info":
        send_message(chat_id, build_info_message())
    elif command == "assets":
        send_message(chat_id, build_assets_message())
    elif command == "sessions":
        send_message(chat_id, build_session_message())
    elif command == "give":
        asset = resolve_asset(arg or "")
        if not asset:
            send_message(chat_id, "Asset nicht gefunden. Nutze <code>/info</code> für alle gültigen Befehle, z. B. <code>/giveBTC</code>.")
        else:
            try:
                send_message(chat_id, build_asset_message(asset))
            except Exception as exc:
                send_message(chat_id, f"⚠️ Konnte Daten für <b>{esc(asset['name'])}</b> gerade nicht laden: {esc(exc)}")
    else:
        send_message(chat_id, "Unbekannter Befehl. Nutze <code>/info</code>.")
    return command


def main() -> None:
    state = load_state()
    offset = int(state.get("last_update_id", 0)) + 1 if state.get("last_update_id") is not None else None
    data = {}
    if offset:
        data["offset"] = str(offset)
    data["timeout"] = "0"
    payload = telegram_request("getUpdates", data)
    updates = payload.get("result", [])
    processed = 0

    for update in updates:
        update_id = update.get("update_id")
        if update_id is not None:
            state["last_update_id"] = max(int(state.get("last_update_id", update_id)), int(update_id))
        message = update.get("message") or update.get("edited_message")
        if not message:
            continue
        result = handle_message(message)
        if result:
            processed += 1

    state["last_checked_at"] = datetime.now(timezone.utc).isoformat()
    state["last_processed_count"] = processed
    save_state(state)
    print(f"Telegram commands checked. Updates: {len(updates)}, processed commands: {processed}")


if __name__ == "__main__":
    main()
