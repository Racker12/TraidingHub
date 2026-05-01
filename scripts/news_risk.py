import os
import re
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "").strip()
BASE_URL = "https://finnhub.io/api/v1"
TIMEZONE = ZoneInfo("Europe/Berlin")

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


def _request_json(path, params=None, timeout=20):
    if not FINNHUB_API_KEY:
        return {"_error": "missing_api_key"}

    params = params or {}
    params["token"] = FINNHUB_API_KEY

    try:
        response = requests.get(f"{BASE_URL}{path}", params=params, timeout=timeout)

        if response.status_code == 429:
            return {"_error": "rate_limit"}

        response.raise_for_status()
        return response.json()

    except Exception as exc:
        return {"_error": str(exc)}


def _text_contains_any(text, keywords):
    text = (text or "").lower()
    return any(keyword.lower() in text for keyword in keywords)


def _clean_title(title):
    title = re.sub(r"\s+", " ", title or "").strip()
    return title[:160]


def _event_datetime_text(event):
    event_time = str(event.get("time", "") or "").strip()
    event_date = str(event.get("date", "") or "").strip()

    if event_time and event_date:
        return f"{event_date} {event_time}"

    if event_time:
        return event_time

    if event_date:
        return event_date

    return ""


def _impact_level_from_event(event):
    title = " ".join([
        str(event.get("event", "")),
        str(event.get("country", "")),
        str(event.get("impact", "")),
    ]).strip()

    text = title.lower()
    impact = str(event.get("impact", "") or "").lower()

    is_high = "high" in impact or _text_contains_any(text, HIGH_IMPACT_KEYWORDS)
    is_medium = "medium" in impact or _text_contains_any(text, MEDIUM_IMPACT_KEYWORDS)

    if is_high:
        return "Hoch"

    if is_medium:
        return "Mittel"

    return "Niedrig"


def get_economic_calendar_risk():
    """
    Prüft wichtige Makroevents heute und morgen.
    Wird im Trading-Score verwendet.
    """
    now = datetime.now(TIMEZONE)
    start = now.date().isoformat()
    end = (now.date() + timedelta(days=1)).isoformat()

    data = _request_json("/calendar/economic", {"from": start, "to": end})

    if not data or isinstance(data, dict) and data.get("_error"):
        error = data.get("_error") if isinstance(data, dict) else "unknown"
        return {
            "score": 0,
            "level": "Unbekannt",
            "reasons": [f"Finnhub Economic Calendar konnte nicht geladen werden: {error}"],
        }

    events = data.get("economicCalendar", []) if isinstance(data, dict) else []

    reasons = []
    score = 0

    for event in events:
        event_name = str(event.get("event", "") or "").strip()
        country = str(event.get("country", "") or "").strip()
        impact = str(event.get("impact", "") or "").strip()

        combined = " ".join([event_name, country, impact]).strip()
        level = _impact_level_from_event(event)

        if level == "Hoch":
            score += 3
            reasons.append(f"Heute/kurzfristig wichtiges Makroevent: {_clean_title(combined)}")
        elif level == "Mittel":
            score += 1
            reasons.append(f"Makroevent im Blick behalten: {_clean_title(combined)}")

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

    # Kein Company-News-Call für Forex, Futures, Crypto-Paare oder europäische/asiatische Ticker.
    if ticker.endswith("=X") or ticker.endswith("=F") or "-" in ticker or "." in ticker:
        return {"score": 0, "level": "Niedrig", "reasons": []}

    now = datetime.now(TIMEZONE)
    start = (now.date() - timedelta(days=2)).isoformat()
    end = now.date().isoformat()

    data = _request_json("/company-news", {"symbol": ticker, "from": start, "to": end})

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
        data = _request_json("/news", {"category": category})

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

    # Doppelte News entfernen, Reihenfolge behalten
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
    Gibt kommende wichtige Makro-Events für die Börsenstatus-Nachricht zurück.
    """
    if not FINNHUB_API_KEY:
        return {
            "level": "Unbekannt",
            "events": ["FINNHUB_API_KEY fehlt. Makro-News konnten nicht geprüft werden."],
        }

    now = datetime.now(TIMEZONE)
    start = now.date().isoformat()
    end = (now.date() + timedelta(days=days_ahead)).isoformat()

    data = _request_json("/calendar/economic", {"from": start, "to": end})

    if not data or isinstance(data, dict) and data.get("_error"):
        error = data.get("_error") if isinstance(data, dict) else "unknown"
        return {
            "level": "Unbekannt",
            "events": [f"Economic Calendar konnte nicht geladen werden: {error}"],
        }

    events = data.get("economicCalendar", []) if isinstance(data, dict) else []

    important = []

    for event in events:
        event_name = str(event.get("event", "") or "").strip()
        country = str(event.get("country", "") or "").strip()
        impact = str(event.get("impact", "") or "").strip()

        combined = " ".join([event_name, country, impact]).strip()
        level = _impact_level_from_event(event)

        if level not in ["Hoch", "Mittel"]:
            continue

        icon = "🔴" if level == "Hoch" else "🟠"
        event_time = _event_datetime_text(event)
        time_part = f"{event_time} - " if event_time else ""
        country_part = f"{country} - " if country else ""
        impact_part = f" ({impact})" if impact else ""

        important.append(
            f"{icon} {time_part}{country_part}{_clean_title(event_name)}{impact_part}"
        )

    if not important:
        return {
            "level": "Niedrig",
            "events": ["Keine wichtigen Makro-Events in den nächsten Tagen erkannt."],
        }

    # Doppelte entfernen
    unique_events = []
    for item in important:
        if item not in unique_events:
            unique_events.append(item)

    level = "Hoch" if any(item.startswith("🔴") for item in unique_events) else "Mittel"

    return {
        "level": level,
        "events": unique_events[:8],
    }
