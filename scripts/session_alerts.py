import json
import os
from datetime import datetime, date, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

STATE_FILE = Path("session_alert_state.json")

LOCAL_TIMEZONE = os.getenv("SESSION_TIMEZONE", "Europe/Berlin")
SEND_INITIAL_SESSION_SUMMARY = os.getenv("SEND_INITIAL_SESSION_SUMMARY", "auto").lower()

BERLIN_TZ = ZoneInfo(LOCAL_TIMEZONE)
NEW_YORK_TZ = ZoneInfo("America/New_York")


# ============================================================
# Telegram
# ============================================================

def send_telegram(message: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN oder TELEGRAM_CHAT_ID fehlt in GitHub Secrets.")

    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        },
        timeout=20,
    )
    response.raise_for_status()


# ============================================================
# State
# ============================================================

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


# ============================================================
# Date helpers
# ============================================================

def is_weekend(day: date) -> bool:
    return day.weekday() >= 5


def easter_sunday(year: int) -> date:
    """
    Gregorian Easter calculation.
    Returns Easter Sunday for given year.
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """
    weekday: Monday=0 ... Sunday=6
    n: 1 = first, 2 = second, etc.
    """
    first = date(year, month, 1)
    days_until = (weekday - first.weekday()) % 7
    return first + timedelta(days=days_until + (n - 1) * 7)


def last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)

    days_back = (last.weekday() - weekday) % 7
    return last - timedelta(days=days_back)


def observed_fixed_holiday(year: int, month: int, day: int) -> date:
    """
    US-style observed holiday.
    If holiday falls Saturday -> Friday before.
    If holiday falls Sunday -> Monday after.
    """
    actual = date(year, month, day)
    if actual.weekday() == 5:
        return actual - timedelta(days=1)
    if actual.weekday() == 6:
        return actual + timedelta(days=1)
    return actual


# ============================================================
# Market calendars
# ============================================================

def lsx_closed_dates(year: int) -> set[date]:
    """
    LSX / Lang & Schwarz relevant non-trading days.
    Dynamic core:
    - New Year
    - Good Friday
    - Easter weekend/Monday
    - Labour Day
    - Christmas Eve
    - Christmas
    - 2nd Christmas Day
    - New Year's Eve

    2026 also includes official/specific dates from Lang & Schwarz calendar.
    """
    easter = easter_sunday(year)

    closed = {
        date(year, 1, 1),
        easter - timedelta(days=2),  # Good Friday
        easter - timedelta(days=1),  # Easter Saturday
        easter,                      # Easter Sunday
        easter + timedelta(days=1),  # Easter Monday
        date(year, 5, 1),
        date(year, 12, 24),
        date(year, 12, 25),
        date(year, 12, 26),
        date(year, 12, 31),
    }

    return closed


def xetra_closed_dates(year: int) -> set[date]:
    """
    Xetra / Deutsche Börse non-trading days.
    Core dates based on Deutsche Börse calendar pattern.
    """
    easter = easter_sunday(year)

    return {
        date(year, 1, 1),
        easter - timedelta(days=2),  # Good Friday
        easter + timedelta(days=1),  # Easter Monday
        date(year, 5, 1),
        date(year, 12, 24),
        date(year, 12, 25),
        date(year, 12, 31),
    }


def us_market_closed_dates(year: int) -> set[date]:
    """
    NYSE/Nasdaq-style US market holidays.
    Includes common full-day closures.
    """
    easter = easter_sunday(year)

    holidays = {
        observed_fixed_holiday(year, 1, 1),       # New Year's Day
        nth_weekday(year, 1, 0, 3),               # Martin Luther King Jr. Day
        nth_weekday(year, 2, 0, 3),               # Presidents' Day
        easter - timedelta(days=2),               # Good Friday
        last_weekday(year, 5, 0),                 # Memorial Day
        observed_fixed_holiday(year, 6, 19),      # Juneteenth
        observed_fixed_holiday(year, 7, 4),       # Independence Day
        nth_weekday(year, 9, 0, 1),               # Labor Day
        nth_weekday(year, 11, 3, 4),              # Thanksgiving
        observed_fixed_holiday(year, 12, 25),     # Christmas
    }

    return holidays


def us_market_early_close_dates(year: int) -> set[date]:
    """
    Typical NYSE early close days.
    Close usually 13:00 New York time.
    """
    thanksgiving = nth_weekday(year, 11, 3, 4)

    early = {
        thanksgiving + timedelta(days=1),  # Day after Thanksgiving
        date(year, 12, 24),                # Christmas Eve, if weekday and not full holiday
    }

    # If July 4 is Saturday/Sunday/observed differently, the adjacent weekday
    # can be early close. For 2026 this is July 3.
    july4 = date(year, 7, 4)
    if july4.weekday() == 5:  # Saturday
        early.add(date(year, 7, 3))
    elif july4.weekday() == 6:  # Sunday
        early.add(date(year, 7, 2))
    else:
        early.add(date(year, 7, 3))

    return {d for d in early if d.weekday() < 5 and d not in us_market_closed_dates(year)}


def lsx_early_close_time(day: date) -> time | None:
    """
    Known LSX special early close.
    Lang & Schwarz lists 30.12.2026 trading until 14:00.
    """
    if day == date(2026, 12, 30):
        return time(14, 0)
    return None


def us_close_time_ny(day: date) -> time:
    """
    Regular NYSE close 16:00 ET.
    Early close usually 13:00 ET.
    """
    if day in us_market_early_close_dates(day.year):
        return time(13, 0)
    return time(16, 0)


def is_lsx_open_day(day: date) -> bool:
    return not is_weekend(day) and day not in lsx_closed_dates(day.year)


def is_xetra_open_day(day: date) -> bool:
    return not is_weekend(day) and day not in xetra_closed_dates(day.year)


def is_us_open_day(day_ny: date) -> bool:
    return not is_weekend(day_ny) and day_ny not in us_market_closed_dates(day_ny.year)


# ============================================================
# Event model
# ============================================================

def berlin_dt_for_local_time(day: date, local_time: time) -> datetime:
    return datetime.combine(day, local_time, tzinfo=BERLIN_TZ)


def berlin_dt_for_ny_time(day_berlin: date, ny_time: time) -> datetime:
    """
    Uses the same calendar day from New York perspective when possible.
    This automatically handles DST differences between Europe and US.
    """
    ny_day = datetime.now(NEW_YORK_TZ).date()

    # For scheduled daily checks, Berlin date and NY date can differ around midnight.
    # For US open/close events, we calculate against the current New York date
    # because the US market calendar belongs to New York.
    ny_dt = datetime.combine(ny_day, ny_time, tzinfo=NEW_YORK_TZ)
    return ny_dt.astimezone(BERLIN_TZ)


def event_status(event_dt: datetime, now: datetime, window_minutes: int = 7) -> bool:
    """
    Returns True if now is at/after event time and within a practical send window.
    Since GitHub Actions may run a few minutes late, we allow a window.
    """
    delta = now - event_dt
    return timedelta(minutes=0) <= delta <= timedelta(minutes=window_minutes)


def has_event_passed_today(event_dt: datetime, now: datetime) -> bool:
    return now >= event_dt


def format_dt(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def build_market_events(now: datetime) -> list[dict]:
    today_berlin = now.date()
    now_ny = now.astimezone(NEW_YORK_TZ)
    today_ny = now_ny.date()

    events = []

    # LSX / Trade Republic
    if is_lsx_open_day(today_berlin):
        lsx_open = berlin_dt_for_local_time(today_berlin, time(7, 30))
        lsx_close_t = lsx_early_close_time(today_berlin) or time(23, 0)
        lsx_close = berlin_dt_for_local_time(today_berlin, lsx_close_t)

        events.append({
            "key": "lsx_open",
            "category": "lsx",
            "title": "LSX / Trade Republic öffnet",
            "emoji": "🟢",
            "dt": lsx_open,
            "impact": "Vor Xetra-Open können Spreads größer sein. Für Aktien/ETFs beginnt der lange LSX-Handel.",
            "message": (
                "🟢 <b>LSX / Trade Republic öffnet</b>\n"
                f"Zeit: <b>{format_dt(lsx_open)}</b> ({LOCAL_TIMEZONE})\n"
                "Handelsfenster: <b>07:30–23:00</b>\n\n"
                "Hinweis: Vor Xetra-Open können Spreads breiter sein."
            ),
        })

        events.append({
            "key": "lsx_close",
            "category": "lsx",
            "title": "LSX / Trade Republic schließt",
            "emoji": "🔴",
            "dt": lsx_close,
            "impact": "LSX-Handel endet. Außerhalb der Handelszeit werden normalerweise keine regulären Kurse gestellt.",
            "message": (
                "🔴 <b>LSX / Trade Republic schließt</b>\n"
                f"Zeit: <b>{format_dt(lsx_close)}</b> ({LOCAL_TIMEZONE})\n\n"
                "Der reguläre LSX-Handel ist beendet."
            ),
        })

    # Xetra / Europe
    if is_xetra_open_day(today_berlin):
        xetra_open = berlin_dt_for_local_time(today_berlin, time(9, 0))
        xetra_close = berlin_dt_for_local_time(today_berlin, time(17, 30))

        events.append({
            "key": "xetra_open",
            "category": "xetra",
            "title": "Xetra / Europa öffnet",
            "emoji": "🇪🇺",
            "dt": xetra_open,
            "impact": "Mehr Liquidität bei deutschen/europäischen Aktien und ETFs. Für LSX oft wichtig wegen fairerer Referenzpreise.",
            "message": (
                "🇪🇺 <b>Xetra / Europa öffnet</b>\n"
                f"Zeit: <b>{format_dt(xetra_open)}</b> ({LOCAL_TIMEZONE})\n"
                "Xetra-Kernhandel: <b>09:00–17:30</b>\n\n"
                "Mehr Liquidität bei deutschen/europäischen Aktien und ETFs."
            ),
        })

        events.append({
            "key": "xetra_close",
            "category": "xetra",
            "title": "Xetra / Europa schließt",
            "emoji": "🔴",
            "dt": xetra_close,
            "impact": "Nach Xetra-Close können Spreads auf LSX breiter werden.",
            "message": (
                "🔴 <b>Xetra / Europa schließt</b>\n"
                f"Zeit: <b>{format_dt(xetra_close)}</b> ({LOCAL_TIMEZONE})\n\n"
                "Nach Xetra-Close können Spreads auf LSX breiter werden."
            ),
        })

    # US market
    if is_us_open_day(today_ny):
        us_open_ny = datetime.combine(today_ny, time(9, 30), tzinfo=NEW_YORK_TZ)
        us_close_ny = datetime.combine(today_ny, us_close_time_ny(today_ny), tzinfo=NEW_YORK_TZ)

        us_open_berlin = us_open_ny.astimezone(BERLIN_TZ)
        us_close_berlin = us_close_ny.astimezone(BERLIN_TZ)

        is_early_close = us_close_time_ny(today_ny) == time(13, 0)

        events.append({
            "key": "us_open",
            "category": "us",
            "title": "US-Börse öffnet",
            "emoji": "🇺🇸",
            "dt": us_open_berlin,
            "impact": "Oft starke Bewegung bei US-Aktien, Nasdaq, S&P 500, Tesla, Nvidia, Amazon, Microsoft und auch US-lastigen ETFs.",
            "message": (
                "🇺🇸 <b>US-Börse öffnet</b>\n"
                f"Zeit Deutschland: <b>{format_dt(us_open_berlin)}</b> ({LOCAL_TIMEZONE})\n"
                "US-Zeit: <b>09:30 New York</b>\n\n"
                "Ab jetzt kommen oft größere Schwankungen bei US-Aktien, Nasdaq, S&P 500 und US-lastigen ETFs."
            ),
        })

        close_extra = "\n⚠️ Heute ist US Early Close." if is_early_close else ""

        events.append({
            "key": "us_close",
            "category": "us",
            "title": "US-Börse schließt",
            "emoji": "🔴",
            "dt": us_close_berlin,
            "impact": "US-Regular-Session endet. Danach kann LSX zwar noch handeln, aber Bewegungen/Spreads können anders werden.",
            "message": (
                "🔴 <b>US-Börse schließt</b>\n"
                f"Zeit Deutschland: <b>{format_dt(us_close_berlin)}</b> ({LOCAL_TIMEZONE})\n"
                f"US-Zeit: <b>{us_close_ny.strftime('%H:%M')} New York</b>{close_extra}\n\n"
                "US-Regular-Session beendet. Danach LSX-Spreads und Liquidität prüfen."
            ),
        })

    return sorted(events, key=lambda item: item["dt"])


# ============================================================
# Status summary
# ============================================================

def current_market_status(now: datetime) -> list[str]:
    today_berlin = now.date()
    now_ny = now.astimezone(NEW_YORK_TZ)
    today_ny = now_ny.date()

    lines = []

    # LSX
    if is_lsx_open_day(today_berlin):
        lsx_open = berlin_dt_for_local_time(today_berlin, time(7, 30))
        lsx_close = berlin_dt_for_local_time(today_berlin, lsx_early_close_time(today_berlin) or time(23, 0))
        if lsx_open <= now < lsx_close:
            lines.append(f"🟢 <b>LSX / Trade Republic</b>: offen bis {format_dt(lsx_close)}")
        elif now < lsx_open:
            lines.append(f"⚪ <b>LSX / Trade Republic</b>: geschlossen, öffnet {format_dt(lsx_open)}")
        else:
            lines.append("⚪ <b>LSX / Trade Republic</b>: heute geschlossen")
    else:
        lines.append("⚪ <b>LSX / Trade Republic</b>: heute kein regulärer Handel")

    # Xetra
    if is_xetra_open_day(today_berlin):
        xetra_open = berlin_dt_for_local_time(today_berlin, time(9, 0))
        xetra_close = berlin_dt_for_local_time(today_berlin, time(17, 30))
        if xetra_open <= now < xetra_close:
            lines.append(f"🟢 <b>Xetra / Europa</b>: offen bis {format_dt(xetra_close)}")
        elif now < xetra_open:
            lines.append(f"⚪ <b>Xetra / Europa</b>: geschlossen, öffnet {format_dt(xetra_open)}")
        else:
            lines.append("⚪ <b>Xetra / Europa</b>: heute geschlossen")
    else:
        lines.append("⚪ <b>Xetra / Europa</b>: heute kein regulärer Handel")

    # US
    if is_us_open_day(today_ny):
        us_open = datetime.combine(today_ny, time(9, 30), tzinfo=NEW_YORK_TZ).astimezone(BERLIN_TZ)
        us_close = datetime.combine(today_ny, us_close_time_ny(today_ny), tzinfo=NEW_YORK_TZ).astimezone(BERLIN_TZ)
        early = " Early Close" if us_close_time_ny(today_ny) == time(13, 0) else ""

        if us_open <= now < us_close:
            lines.append(f"🟢 <b>US-Börse</b>: offen bis {format_dt(us_close)}{early}")
        elif now < us_open:
            lines.append(f"⚪ <b>US-Börse</b>: geschlossen, öffnet {format_dt(us_open)}")
        else:
            lines.append("⚪ <b>US-Börse</b>: heute geschlossen")
    else:
        lines.append("⚪ <b>US-Börse</b>: heute kein regulärer Handel")

    return lines


def next_event_text(now: datetime, events: list[dict]) -> str:
    future = [event for event in events if event["dt"] > now]
    if future:
        event = future[0]
        return f"{event['emoji']} {event['title']} um {format_dt(event['dt'])}"

    return "Heute keine weiteren wichtigen Börsen-Events."


def summary_message(now: datetime) -> str:
    events = build_market_events(now)
    status = "\n".join(current_market_status(now))

    return (
        "🕒 <b>Aktueller Börsenstatus für LSX / Trade Republic</b>\n"
        f"Zeit: <b>{now.strftime('%Y-%m-%d %H:%M')}</b> ({LOCAL_TIMEZONE})\n\n"
        f"{status}\n\n"
        f"<b>Nächstes wichtiges Event:</b>\n{next_event_text(now, events)}\n\n"
        "Berücksichtigt werden Wochenende, LSX/Xetra-Feiertage, US-Feiertage und US-Sommerzeit."
    )


# ============================================================
# Sending logic
# ============================================================

def event_state_key(event: dict) -> str:
    return f"{event['dt'].date().isoformat()}:{event['key']}"


def should_send_event(state: dict, event: dict, now: datetime) -> bool:
    key = event_state_key(event)
    if state.get("events_sent", {}).get(key):
        return False

    return event_status(event["dt"], now, window_minutes=12)


def mark_event_sent(state: dict, event: dict, now: datetime) -> None:
    state.setdefault("events_sent", {})
    state["events_sent"][event_state_key(event)] = {
        "sent_at_local": now.isoformat(),
        "event_time_local": event["dt"].isoformat(),
        "title": event["title"],
    }


def cleanup_old_events(state: dict, now: datetime, keep_days: int = 14) -> None:
    events_sent = state.get("events_sent", {})
    if not isinstance(events_sent, dict):
        state["events_sent"] = {}
        return

    cutoff = now.date() - timedelta(days=keep_days)
    cleaned = {}

    for key, value in events_sent.items():
        try:
            day_string = key.split(":")[0]
            event_day = date.fromisoformat(day_string)
            if event_day >= cutoff:
                cleaned[key] = value
        except Exception:
            continue

    state["events_sent"] = cleaned


def should_send_initial_summary(state: dict) -> bool:
    if SEND_INITIAL_SESSION_SUMMARY == "true":
        return True

    if SEND_INITIAL_SESSION_SUMMARY == "false":
        return False

    # auto: Beim manuellen Run Status senden, damit du testen kannst.
    run_id = os.getenv("GITHUB_RUN_ID", "")
    last_manual_run_id = state.get("last_manual_summary_run_id")

    return (
        os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch"
        and run_id
        and run_id != last_manual_run_id
    )


def save_manual_summary_marker(state: dict) -> None:
    run_id = os.getenv("GITHUB_RUN_ID", "")
    if run_id:
        state["last_manual_summary_run_id"] = run_id


def main() -> None:
    now = datetime.now(BERLIN_TZ)
    state = load_state()
    cleanup_old_events(state, now)

    alerts_sent = 0

    if should_send_initial_summary(state):
        send_telegram(summary_message(now))
        save_manual_summary_marker(state)
        alerts_sent += 1

    events = build_market_events(now)

    for event in events:
        print(
            f"Event {event['key']}: {event['title']} at "
            f"{event['dt'].strftime('%Y-%m-%d %H:%M %Z')}"
        )

        if should_send_event(state, event, now):
            send_telegram(event["message"])
            mark_event_sent(state, event, now)
            alerts_sent += 1
            print(f"SENT {event['key']}")

    state["last_checked_at_local"] = now.isoformat()
    state["last_checked_at_utc"] = datetime.now(timezone.utc).isoformat()
    state["current_status"] = current_market_status(now)
    state["today_events"] = [
        {
            "key": event["key"],
            "title": event["title"],
            "time_local": event["dt"].isoformat(),
        }
        for event in events
    ]

    save_state(state)

    print(f"Session/market alerts sent: {alerts_sent}")


if __name__ == "__main__":
    main()
