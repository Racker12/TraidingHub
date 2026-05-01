import os
import re
import time
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "").strip()
BASE_URL = "https://finnhub.io/api/v1"

TIMEZONE = ZoneInfo("Europe/Berlin")
UTC_TZ = ZoneInfo("UTC")

REQUEST_TIMEOUT = 45
REQUEST_RETRIES = 3

# Economic Events werden nur berücksichtigt, wenn sie noch kommen
# oder maximal so viele Minuten zurückliegen.
EVENT_PAST_WINDOW_MINUTES = int(os.getenv("NEWS_EVENT_PAST_WINDOW_MINUTES", "60"))

ECONOMIC_CACHE = {}
MARKET_NEWS_CACHE = {}
COMPANY_NEWS_CACHE = {}

HIGH_IMPACT_KEYWORDS = [
    "cpi", "inflation", "consumer price index",
    "fomc", "fed", "federal reserve", "powell",
    "interest rate", "rate decision", "rate hike", "rate cut",
    "nfp", "nonfarm", "non-farm", "payrolls",
    "unemployment", "jobs report",
    "pce", "core pce",
    "ecb", "lagarde",
    "gdp", "retail sales",
    "war", "attack", "sanction", "crisis",
    "ism", "pmi", "jobless claims",
    "jolts", "consumer confidence",
]

MEDIUM_IMPACT_KEYWORDS = [
    "earnings", "guidance", "forecast", "outlook",
    "revenue", "profit", "loss",
    "sec", "lawsuit", "investigation",
    "downgrade", "upgrade", "price target",
    "oil", "dollar", "yields", "treasury",
    "speech", "minutes", "auction",
]

# Diese Begriffe sind so wichtig, dass selbst ein Finnhub-"Low" nicht komplett ignoriert wird.
# Aber sie werden dann nur auf "Mittel" hochgestuft, nicht auf "Hoch".
CRITICAL_LOW_UPGRADE_KEYWORDS = [
    "cpi",
    "consumer price index",
    "fomc",
    "fed rate decision",
    "federal funds rate",
    "interest rate decision",
    "rate decision",
    "nfp",
    "nonfarm",
    "non-farm",
    "payrolls",
    "pce",
    "core pce",
    "ecb rate decision",
    "deposit facility rate",
    "main refinancing rate",
]

ASSET_KEYWORDS = {
    "BTC": ["bitcoin", "btc", "crypto", "cryptocurrency"],
    "ETH": ["ethereum", "eth", "crypto", "cryptocurrency"],
    "SOL": ["solana", "sol", "crypto", "cryptocurrency"],

    "XAU": ["gold", "xau", "precious metals", "fed", "inflation", "dollar", "yields"],
    "SI": ["silver", "si", "precious metals", "fed", "inflation", "dollar", "yields"],
    "PL": ["platinum", "platin", "precious metals", "commodity"],

    "EURUSD": ["eurusd", "euro", "ecb", "fed", "inflation", "dollar"],
    "GBPUSD": ["gbpusd", "pound", "bank of england", "boe", "fed", "inflation"],
    "USDJPY": ["usdjpy", "yen", "boj", "bank of japan", "fed", "dollar"],

    "NASDAQ": ["nasdaq", "technology", "tech stocks", "fed", "inflation", "yields"],
    "Tesla": ["tesla", "tsla", "elon musk", "ev"],
    "NVD": ["nvidia", "nvda", "ai chips", "semiconductor"],
    "APC": ["apple", "aapl", "iphone"],
    "AMZ": ["amazon", "amzn", "aws"],
    "MSF": ["microsoft", "msft", "azure"],
    "BYD": ["byd", "electric vehicle", "ev"],
    "RheinmetallAG": ["rheinmetall", "defense", "defence", "rüstung"],
    "VWCE": ["vanguard", "ftse all-world", "world etf", "etf"],
    "ABEA": ["aex", "netherlands", "europe stocks"],
}


def _request_json(path, params=None, timeout=REQUEST_TIMEOUT):
    if not FINNHUB_API_KEY:
        return {"_error": "missing_api_key"}

    params = params or {}
    params["token"] = FINNHUB_API_KEY

    last_error = None

    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            response = requests.get(
                f"{BASE_URL}{path}",
                params=params,
                timeout=timeout,
            )

            if response.status_code == 429:
                return {"_error": "rate_limit"}

            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout:
            last_error = f"timeout_attempt_{attempt}"
            time.sleep(2 * attempt)

        except Exception as exc:
            last_error = str(exc)
            time.sleep(1 * attempt)

    return {"_error": last_error or "unknown_error"}


def _text_contains_any(text, keywords):
    text = (text or "").lower()
    return any(keyword.lower() in text for keyword in keywords)


def _clean_title(title):
    title = re.sub(r"\s+", " ", title or "").strip()
    return title[:160]


def _impact_level_from_event(event):
    """
    Einheitliche News-Bewertung:

    - Finnhub High -> Hoch
    - Finnhub Medium -> Mittel
    - Finnhub Low -> normalerweise Niedrig / wird ausgefiltert
    - Finnhub Low + extrem wichtige Begriffe -> Mittel
    - Kein Impact-Feld + wichtige Begriffe -> Mittel/Hoch

    Dadurch gibt es keine widersprüchliche Anzeige mehr wie:
    🔴 Event (Low)
    """
    event_name = str(event.get("event", "") or "")
    country = str(event.get("country", "") or "")
    impact = str(event.get("impact", "") or "").lower()

    text = f"{event_name} {country} {impact}".lower()

    has_critical_keyword = _text_contains_any(text, CRITICAL_LOW_UPGRADE_KEYWORDS)
    has_high_keyword = _text_contains_any(text, HIGH_IMPACT_KEYWORDS)
    has_medium_keyword = _text_contains_any(text, MEDIUM_IMPACT_KEYWORDS)

    if "high" in impact:
        return "Hoch"

    if "medium" in impact:
        return "Mittel"

    if "low" in impact:
        if has_critical_keyword:
            return "Mittel"
        return "Niedrig"

    if has_critical_keyword:
        return "Hoch"

    if has_high_keyword:
        return "Mittel"

    if has_medium_keyword:
        return "Mittel"

    return "Niedrig"


def _parse_event_datetime_de(event):
    """
    Finnhub Economic Calendar liefert meist date + time.
    Wir interpretieren diese Zeit als UTC und rechnen sie nach Europe/Berlin um.

    Auch 00:00:00 wird als echte Zeit behandelt, weil Finnhub manchmal
    mehrere Events um 00:00, 00:01, 00:30 usw. liefert.
    """
    event_date = str(event.get("date", "") or "").strip()
    event_time = str(event.get("time", "") or "").strip()

    if not event_date and not event_time:
        return None

    raw = f"{event_date} {event_time}".strip()

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%H:%M:%S",
        "%H:%M",
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(raw, fmt)

            # Falls nur eine Uhrzeit ohne Datum geliefert wird
            if parsed.year == 1900:
                today = datetime.now(TIMEZONE).date()
                parsed = parsed.replace(
                    year=today.year,
                    month=today.month,
                    day=today.day,
                )

            # Finnhub-Zeit als UTC interpretieren und nach deutscher Zeit umrechnen
            parsed_utc = parsed.replace(tzinfo=UTC_TZ)
            return parsed_utc.astimezone(TIMEZONE)

        except Exception:
            continue

    return None


def _event_datetime_text(event):
    dt_de = _parse_event_datetime_de(event)

    if dt_de:
        return dt_de.strftime("%d.%m.%Y %H:%M Uhr DE")

    event_time = str(event.get("time", "") or "").strip()
    event_date = str(event.get("date", "") or "").strip()

    if event_time and event_date:
        return f"{event_date} {event_time} laut Finnhub"

    if event_time:
        return f"{event_time} laut Finnhub"

    if event_date:
        return f"{event_date} laut Finnhub"

    return ""


def _event_is_relevant_time(event, days_ahead=2):
    """
    True nur wenn:
    - Event liegt noch in der Zukunft
    - oder Event war maximal EVENT_PAST_WINDOW_MINUTES Minuten her

    Dadurch verschwinden alte Events vom Morgen/Tag aus der Übersicht.
    """
    dt_de = _parse_event_datetime_de(event)

    if not dt_de:
        # Wenn keine Zeit parsebar ist, lieber nicht anzeigen,
        # damit keine alten/unklaren Events stören.
        return False

    now = datetime.now(TIMEZONE)
    earliest_allowed = now - timedelta(minutes=EVENT_PAST_WINDOW_MINUTES)
    latest_allowed = now + timedelta(days=days_ahead)

    return earliest_allowed <= dt_de <= latest_allowed


def _get_economic_calendar_data(days_ahead=2):
    """
    Economic Calendar wird pro days_ahead gecacht.
    """
    cache_key = f"economic_{days_ahead}"

    if cache_key in ECONOMIC_CACHE:
        return ECONOMIC_CACHE[cache_key]

    now = datetime.now(TIMEZONE)
    start = now.date().isoformat()
    end = (now.date() + timedelta(days=days_ahead)).isoformat()

    data = _request_json("/calendar/economic", {"from": start, "to": end})
    ECONOMIC_CACHE[cache_key] = data
    return data


def _get_market_news_data(category):
    if category in MARKET_NEWS_CACHE:
        return MARKET_NEWS_CACHE[category]

    data = _request_json("/news", {"category": category})
    MARKET_NEWS_CACHE[category] = data
    return data


def _get_company_news_data(ticker):
    if ticker in COMPANY_NEWS_CACHE:
        return COMPANY_NEWS_CACHE[ticker]

    now = datetime.now(TIMEZONE)
    start = (now.date() - timedelta(days=2)).isoformat()
    end = now.date().isoformat()

    data = _request_json("/company-news", {"symbol": ticker, "from": start, "to": end})
    COMPANY_NEWS_CACHE[ticker] = data
    return data


def get_economic_calendar_risk():
    """
    Prüft wichtige Makroevents.
    Es werden nur Events berücksichtigt, die noch bevorstehen
    oder maximal EVENT_PAST_WINDOW_MINUTES Minuten zurückliegen.
    """
    data = _get_economic_calendar_data(days_ahead=1)

    if not data or isinstance(data, dict) and data.get("_error"):
        error = data.get("_error") if isinstance(data, dict) else "unknown"
        return {
            "score": 0,
            "level": "Unbekannt",
            "reasons": [f"Finnhub Economic Calendar temporär nicht erreichbar: {error}"],
        }

    events = data.get("economicCalendar", []) if isinstance(data, dict) else []

    reasons = []
    score = 0

    for event in events:
        if not _event_is_relevant_time(event, days_ahead=1):
            continue

        event_name = str(event.get("event", "") or "").strip()
        country = str(event.get("country", "") or "").strip()
        impact = str(event.get("impact", "") or "").strip()

        combined = " ".join([event_name, country, impact]).strip()
        level = _impact_level_from_event(event)

        when = _event_datetime_text(event)
        when_part = f"{when} - " if when else ""

        if level == "Hoch":
            score += 3
            reasons.append(f"{when_part}Wichtiges Makroevent: {_clean_title(combined)}")
        elif level == "Mittel":
            score += 1
            reasons.append(f"{when_part}Makroevent im Blick behalten: {_clean_title(combined)}")

    return {
        "score": min(score, 6),
        "level": "Hoch" if score >= 4 else "Mittel" if score >= 2 else "Niedrig",
        "reasons": reasons[:5],
    }


def get_company_news_risk(asset):
    """
    Prüft Company News bei US-Aktien.
    Für Forex, Krypto, Futures und europäische Ticker wird dieser Block übersprungen.
    """
    ticker = asset.get("ticker", "")
    key = asset.get("key", "")

    if ticker.endswith("=X") or ticker.endswith("=F") or "-" in ticker or "." in ticker:
        return {"score": 0, "level": "Niedrig", "reasons": []}

    data = _get_company_news_data(ticker)

    if not data or isinstance(data, dict) and data.get("_error"):
        return {"score": 0, "level": "Unbekannt", "reasons": []}

    reasons = []
    score = 0

    for item in data[:12]:
        headline = item.get("headline", "")
        summary = item.get("summary", "")
        text = f"{headline} {summary}".lower()

        if _text_contains_any(text, HIGH_IMPACT_KEYWORDS):
            score += 2
            reasons.append(f"Wichtige Asset-News: {_clean_title(headline)}")
        elif _text_contains_any(text, MEDIUM_IMPACT_KEYWORDS):
            score += 1
            reasons.append(f"Asset-News: {_clean_title(headline)}")
        elif key in ASSET_KEYWORDS and _text_contains_any(text, ASSET_KEYWORDS[key]):
            score += 1
            reasons.append(f"Neue Asset-News: {_clean_title(headline)}")

    return {
        "score": min(score, 5),
        "level": "Hoch" if score >= 4 else "Mittel" if score >= 2 else "Niedrig",
        "reasons": reasons[:4],
    }


def get_market_news_risk(asset):
    """
    Prüft allgemeine Market News und sucht nach Keywords passend zum Asset.
    """
    key = asset.get("key", "")
    group = asset.get("group", "")
    keywords = ASSET_KEYWORDS.get(key, [key.lower(), asset.get("name", "").lower()])

    categories = ["general"]

    if group == "crypto" or key in ["BTC", "ETH", "SOL"]:
        categories = ["crypto", "general"]
    elif key in ["XAU", "SI", "PL"]:
        categories = ["forex", "general"]
    elif group in ["forex_major", "usd_jpy"]:
        categories = ["forex", "general"]

    reasons = []
    score = 0

    for category in categories:
        data = _get_market_news_data(category)

        if not data or isinstance(data, dict) and data.get("_error"):
            continue

        for item in data[:25]:
            headline = item.get("headline", "")
            summary = item.get("summary", "")
            text = f"{headline} {summary}".lower()

            asset_related = _text_contains_any(text, keywords)
            high_related = _text_contains_any(text, HIGH_IMPACT_KEYWORDS)
            medium_related = _text_contains_any(text, MEDIUM_IMPACT_KEYWORDS)

            if asset_related and high_related:
                score += 2
                reasons.append(f"Markt-/Asset-News: {_clean_title(headline)}")
            elif asset_related and medium_related:
                score += 1
                reasons.append(f"Relevante News: {_clean_title(headline)}")
            elif high_related and key in [
                "BTC", "ETH", "SOL", "XAU", "SI", "PL",
                "EURUSD", "GBPUSD", "USDJPY", "NASDAQ"
            ]:
                score += 1
                reasons.append(f"Makro/Markt-News relevant: {_clean_title(headline)}")

    unique_reasons = []
    for reason in reasons:
        if reason not in unique_reasons:
            unique_reasons.append(reason)

    return {
        "score": min(score, 5),
        "level": "Hoch" if score >= 4 else "Mittel" if score >= 2 else "Niedrig",
        "reasons": unique_reasons[:5],
    }


def get_news_risk(asset):
    """
    Einheitliches News-Risiko für Trading-Score-Alerts:
    Niedrig / Mittel / Hoch / Unbekannt
    """
    if not FINNHUB_API_KEY:
        return {
            "level": "Unbekannt",
            "score": 0,
            "reasons": ["FINNHUB_API_KEY fehlt. News-Risiko wurde nicht geprüft."],
        }

    macro = get_economic_calendar_risk()
    company = get_company_news_risk(asset)
    market = get_market_news_risk(asset)

    total = macro.get("score", 0) + company.get("score", 0) + market.get("score", 0)

    reasons = []
    for block in [macro, company, market]:
        for reason in block.get("reasons", []):
            if reason and reason not in reasons:
                reasons.append(reason)

    if total >= 6:
        level = "Hoch"
    elif total >= 3:
        level = "Mittel"
    else:
        level = "Niedrig"

    if not reasons:
        reasons = ["Keine stark relevanten News erkannt."]

    return {
        "level": level,
        "score": total,
        "reasons": reasons[:6],
    }


def get_upcoming_important_events(days_ahead=2):
    """
    Wird von session_alerts.py beim manuellen Workflow-Start genutzt.

    Gibt nur Events zurück, die:
    - noch bevorstehen
    - oder maximal EVENT_PAST_WINDOW_MINUTES Minuten zurückliegen

    Angezeigt werden nur:
    - Hoch
    - Mittel

    Niedrig wird aussortiert, außer es enthält extrem wichtige Begriffe
    und wird dadurch auf Mittel hochgestuft.
    """
    if not FINNHUB_API_KEY:
        return {
            "level": "Unbekannt",
            "events": ["FINNHUB_API_KEY fehlt. Makro-News konnten nicht geprüft werden."],
        }

    data = _get_economic_calendar_data(days_ahead=days_ahead)

    if not data or isinstance(data, dict) and data.get("_error"):
        error = data.get("_error") if isinstance(data, dict) else "unknown"
        return {
            "level": "Unbekannt",
            "events": [f"Economic Calendar temporär nicht erreichbar: {error}"],
        }

    events = data.get("economicCalendar", []) if isinstance(data, dict) else []

    important = []

    for event in events:
        if not _event_is_relevant_time(event, days_ahead=days_ahead):
            continue

        event_name = str(event.get("event", "") or "").strip()
        country = str(event.get("country", "") or "").strip()

        level = _impact_level_from_event(event)

        if level not in ["Hoch", "Mittel"]:
            continue

        icon = "🔴" if level == "Hoch" else "🟠"
        event_time = _event_datetime_text(event)
        time_part = f"{event_time} - " if event_time else ""
        country_part = f"{country} - " if country else ""

        important.append(
            f"{icon} {time_part}{country_part}{_clean_title(event_name)} | Risiko: {level}"
        )

    if not important:
        return {
            "level": "Niedrig",
            "events": ["Keine wichtigen Makro-Events mehr in den nächsten Tagen erkannt."],
        }

    unique_events = []
    for item in important:
        if item not in unique_events:
            unique_events.append(item)

    level = "Hoch" if any(item.startswith("🔴") for item in unique_events) else "Mittel"

    return {
        "level": level,
        "events": unique_events[:8],
    }
