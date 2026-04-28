import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

STATE_FILE = Path("session_alert_state.json")
LOCAL_TIMEZONE = os.getenv("SESSION_TIMEZONE", "Europe/Berlin")
SEND_INITIAL_SESSION_SUMMARY = os.getenv("SEND_INITIAL_SESSION_SUMMARY", "auto").lower()

# Gleiche Session-Logik wie in der Website, aber serverfest über eine feste Zeitzone.
# Zeiten sind als lokale Stunden in SESSION_TIMEZONE hinterlegt.
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


def send_telegram(message: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN oder TELEGRAM_CHAT_ID fehlt in GitHub Secrets.")

    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": message, "parse_mode": "HTML", "disable_web_page_preview": "true"},
        timeout=20,
    )
    response.raise_for_status()


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


def time_to_next_boundary(session: dict, hour: float, currently_open: bool) -> float:
    target = session["close"] if currently_open else session["open"]
    return (target - hour + 24) % 24


def build_status_lines(now: datetime):
    hour = local_hour(now)
    lines = []
    open_names = []
    for session in SESSIONS:
        current = is_open(session, hour)
        until = time_to_next_boundary(session, hour, current)
        if current:
            open_names.append(session["name"])
            lines.append(f"🟢 <b>{session['name']}</b>: offen bis {fmt_hour(session['close'])} ({until:.1f}h)")
        else:
            lines.append(f"⚪ <b>{session['name']}</b>: geschlossen, öffnet {fmt_hour(session['open'])} ({until:.1f}h)")
    return open_names, lines


def summary_message(now: datetime) -> str:
    open_names, lines = build_status_lines(now)
    active = ", ".join(open_names) if open_names else "keine Session offen"
    return (
        "🕒 <b>Aktuelle Trading Sessions</b>\n"
        f"Zeit: <b>{now.strftime('%Y-%m-%d %H:%M')}</b> ({LOCAL_TIMEZONE})\n"
        f"Aktiv: <b>{active}</b>\n\n"
        + "\n".join(lines)
        + "\n\nHinweis: Sessionzeiten sind die in deiner Website genutzten Richtwerte. Feiertage/Sonderzeiten werden nicht automatisch berücksichtigt."
    )


def transition_message(session: dict, now: datetime, opened: bool) -> str:
    hour = local_hour(now)
    current = is_open(session, hour)
    until = time_to_next_boundary(session, hour, current)
    event = "öffnet" if opened else "schließt"
    emoji = "🟢" if opened else "🔴"
    next_text = f"schließt um {fmt_hour(session['close'])}" if opened else f"öffnet wieder um {fmt_hour(session['open'])}"
    return (
        f"{emoji} <b>Session Alert</b>\n"
        f"<b>{session['name']}</b> {event} jetzt.\n"
        f"Zeit: <b>{now.strftime('%Y-%m-%d %H:%M')}</b> ({LOCAL_TIMEZONE})\n"
        f"Nächster Status: {next_text} ({until:.1f}h)\n\n"
        "Bitte News, Spread und Volatilität prüfen, bevor du tradest."
    )


def should_send_initial_summary(state: dict) -> bool:
    if SEND_INITIAL_SESSION_SUMMARY == "true":
        return True
    if SEND_INITIAL_SESSION_SUMMARY == "false":
        return False
    # auto: beim manuellen GitHub-Run einmal Status senden, damit du direkt prüfen kannst, ob alles funktioniert.
    return os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch" and not state.get("manual_summary_sent")


def main() -> None:
    tz = ZoneInfo(LOCAL_TIMEZONE)
    now = datetime.now(tz)
    hour = local_hour(now)
    state = load_state()
    alerts_sent = 0

    if should_send_initial_summary(state):
        send_telegram(summary_message(now))
        state["manual_summary_sent"] = True
        alerts_sent += 1

    for session in SESSIONS:
        key = session["name"].lower().replace(" ", "_")
        current = is_open(session, hour)
        previous = state.get(key, {}).get("is_open")

        if previous is not None and previous != current:
            send_telegram(transition_message(session, now, opened=current))
            alerts_sent += 1

        state[key] = {
            "is_open": current,
            "open": fmt_hour(session["open"]),
            "close": fmt_hour(session["close"]),
            "checked_at_local": now.isoformat(),
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        }

        print(f"OK {session['name']}: {'open' if current else 'closed'}")

    state["last_current_sessions"] = build_status_lines(now)[0]
    state["last_checked_at_local"] = now.isoformat()
    save_state(state)
    print(f"Session alerts sent: {alerts_sent}")


if __name__ == "__main__":
    main()
