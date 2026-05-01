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
]

MEDIUM_IMPACT_KEYWORDS = [
    "earnings", "guidance", "forecast", "outlook",
    "revenue", "profit", "loss",
    "sec", "lawsuit", "investigation",
    "downgrade", "upgrade", "price target",
    "oil", "dollar", "yields", "treasury",
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
    "VWCE": ["vanguard", "ftse all-world", "world etf"],
    "ABEA": ["aex", "netherlands", "europe stocks"],
}


def _request_json(path, params=None, timeout=20):
    if not FINNHUB_API_KEY:
        return None

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


def get_economic_calendar_risk():
    """
    Prüft wichtige Makroevents heute und morgen.
    Finnhub Economic Calendar kann je nach Plan/Limit unterschiedlich viele Details liefern.
    """
    now = datetime.now(TIMEZONE)
    start = now.date().isoformat()
    end = (now.date() + timedelta(days=1)).isoformat()

    data = _request_json("/calendar/economic", {"from": start, "to": end})

    reasons = []
    score = 0

    if not data or isinstance(data, dict) and data.get("_error"):
        return {
            "score": 0,
            "level": "Unbekannt",
            "reasons": ["Finnhub Economic Calendar konnte nicht geladen werden."],
        }

    events = data.get("economicCalendar", []) if isinstance(data, dict) else []

    for event in events:
        title = " ".join([
            str(event.get("event", "")),
            str(event.get("country", "")),
            str(event.get("impact", "")),
        ]).strip()

        impact = str(event.get("impact", "")).lower()
        title_lower = title.lower()

        is_high_keyword = _text_contains_any(title_lower, HIGH_IMPACT_KEYWORDS)
        is_medium_keyword = _text_contains_any(title_lower, MEDIUM_IMPACT_KEYWORDS)

        if "high" in impact or is_high_keyword:
            score += 3
            reasons.append(f"Heute/kurzfristig wichtiges Makroevent: {_clean_title(title)}")
        elif "medium" in impact or is_medium_keyword:
            score += 1
            reasons.append(f"Makroevent im Blick behalten: {_clean_title(title)}")

    return {
        "score": min(score, 6),
        "level": "Hoch" if score >= 4 else "Mittel" if score >= 2 else "Niedrig",
        "reasons": reasons[:5],
    }


def get_company_news_risk(asset):
    """
    Prüft Company News bei US-Aktien.
    Für Nicht-US/Forex/Commodities nutzt der Bot eher Market News + Makro.
    Finnhub Company News ist vor allem für nordamerikanische Unternehmen gedacht.
    """
    ticker = asset.get("ticker", "")
    key = asset.get("key", "")

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

    for item in data[:10]:
        headline = item.get("headline", "")
        summary = item.get("summary", "")
        text = f"{headline} {summary}".lower()

        if _text_contains_any(text, HIGH_IMPACT_KEYWORDS):
            score += 2
            reasons.append(f"Wichtige Asset-News: {_clean_title(headline)}")
        elif _text_contains_any(text, MEDIUM_IMPACT_KEYWORDS):
            score += 1
            reasons.append(f"Asset-News: {_clean_title(headline)}")

    return {
        "score": min(score, 5),
        "level": "Hoch" if score >= 4 else "Mittel" if score >= 2 else "Niedrig",
        "reasons": reasons[:4],
    }


def get_market_news_risk(asset):
    """
    Prüft allgemeine Market News und sucht nach Keywords passend zum Asset.
    Finnhub Market News liefert allgemeine News-Kategorien.
    """
    key = asset.get("key", "")
    keywords = ASSET_KEYWORDS.get(key, [key.lower(), asset.get("name", "").lower()])

    categories = ["general"]
    if asset.get("group") == "crypto" or key in ["BTC", "ETH", "SOL"]:
        categories = ["crypto", "general"]
    elif key in ["XAU", "SI", "PL"]:
        categories = ["forex", "general"]
    elif asset.get("group") in ["forex_major", "usd_jpy"]:
        categories = ["forex", "general"]

    reasons = []
    score = 0

    for category in categories:
        data = _request_json("/news", {"category": category})

        if not data or isinstance(data, dict) and data.get("_error"):
            continue

        for item in data[:20]:
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
            elif high_related and key in ["BTC", "ETH", "SOL", "XAU", "SI", "PL", "EURUSD", "GBPUSD", "USDJPY", "NASDAQ"]:
                score += 1
                reasons.append(f"Makro/Markt-News relevant: {_clean_title(headline)}")

    return {
        "score": min(score, 5),
        "level": "Hoch" if score >= 4 else "Mittel" if score >= 2 else "Niedrig",
        "reasons": reasons[:5],
    }


def get_news_risk(asset):
    """
    Gibt ein einheitliches News-Risiko zurück:
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
