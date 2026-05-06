"""
📈 Aktien-Alarm Bot — GitHub Actions
Fixes: EUR/USD korrekt, schöneres Format, RSS News
"""

import os, json, requests, time, re
from datetime import datetime
from xml.etree import ElementTree
import pytz
import yfinance as yf

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

ALARM_SCHWELLE_PCT = 3.0
STATE_FILE         = "kurse_state.json"
DE_TZ              = pytz.timezone("Europe/Berlin")
US_TZ              = pytz.timezone("America/New_York")

KRYPTO = {
    "BTC":  ("Bitcoin",        "bitcoin"),
    "ETH":  ("Ethereum",       "ethereum"),
    "SOL":  ("Solana",         "solana"),
    "HYPE": ("Hyperliquid",    "hyperliquid"),
}

STOCKS = {
    "AMD":   "AMD",          "INTC":  "Intel",
    "MU":    "Micron",       "NOW":   "ServiceNow",
    "SNDK":  "SanDisk",      "CRWV":  "CoreWeave",
    "CRCL":  "Circle",       "NBIS":  "Nebius",
    "CGEH":  "CGEH",         "HOOD":  "Robinhood",
    "RKLB":  "Rocket Lab",   "BE":    "Bloom Energy",
    "IREN":  "Iris Energy",  "WDC":   "Western Digital",
    "CAT":   "Caterpillar",  "TEAM":  "Atlassian",
    "FLY":   "Firefly",      "SMEGF": "Siemens Energy",
    "SSNLF": "Samsung",      "GC=F":  "Gold",
    "SI=F":  "Silber",
}

GRUPPEN = {
    "🪙 KRYPTO":     ["BTC",  "ETH",  "SOL",  "HYPE"],
    "💾 HALBLEITER": ["AMD",  "INTC", "MU",   "NOW",  "SNDK", "CRWV", "CRCL", "NBIS", "CGEH"],
    "📈 AKTIEN":     ["HOOD", "RKLB", "BE",   "IREN", "WDC",  "CAT",  "TEAM", "FLY",  "SMEGF", "SSNLF"],
    "🪨 ROHSTOFFE":  ["GC=F", "SI=F"],
}

def eur_rate() -> float:
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=USD&to=EUR", timeout=8)
        if r.ok:
            return round(float(r.json()["rates"]["EUR"]), 4)
    except Exception as e:
        print(f"  [EUR] {e}")
    try:
        eurusd = float(yf.Ticker("EURUSD=X").fast_info.last_price)
        if eurusd > 0:
            return round(1.0 / eurusd, 4)
    except Exception:
        pass
    return 0.91

def coingecko_kurse() -> dict[str, float]:
    ids = ",".join(cid for _, cid in KRYPTO.values())
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ids, "vs_currencies": "usd"}, timeout=15)
        if r.ok:
            data = r.json()
            return {s: round(float(data[cid]["usd"]), 6)
                    for s, (_, cid) in KRYPTO.items() if cid in data}
    except Exception as e:
        print(f"  [CoinGecko] {e}")
    return {}

def yfinance_kurse() -> dict[str, float]:
    tickers = list(STOCKS.keys())
    result  = {}
    try:
        data   = yf.download(tickers, period="1d", interval="1m",
                              progress=False, threads=True, auto_adjust=True)
        closes = data["Close"]
        for t in tickers:
            try:
                last = closes[t].dropna().iloc[-1]
                if last and float(last) > 0:
                    result[t] = round(float(last), 6)
            except Exception:
                pass
    except Exception as e:
        print(f"  [yf batch] {e}")
    for t in [x for x in tickers if x not in result]:
        try:
            p = yf.Ticker(t).fast_info.last_price
            if p and float(p) > 0:
                result[t] = round(float(p), 6)
            time.sleep(0.2)
        except Exception:
            pass
    return result

def alle_kurse() -> dict[str, float]:
    kurse = coingecko_kurse()
    kurse.update(yfinance_kurse())
    return kurse

def state_laden() -> dict:
    try:
        with open(STATE_FILE) as f: return json.load(f)
    except Exception: return {}

def state_speichern(kurse: dict) -> None:
    with open(STATE_FILE, "w") as f: json.dump(kurse, f)

RSS_FEEDS = [
    ("🌍 Märkte",    "https://feeds.reuters.com/reuters/businessNews"),
    ("🌍 Märkte",    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
    ("₿ Krypto",    "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("₿ Krypto",    "https://cointelegraph.com/rss"),
    ("💾 Tech",      "https://feeds.reuters.com/reuters/technologyNews"),
    ("📈 Aktien",    "https://finance.yahoo.com/rss/headline?s=AMD"),
    ("📈 Aktien",    "https://finance.yahoo.com/rss/headline?s=HOOD"),
    ("🚀 Watchlist", "https://finance.yahoo.com/rss/headline?s=RKLB"),
    ("🚀 Watchlist", "https://finance.yahoo.com/rss/headline?s=CRWV"),
    ("🚀 Watchlist", "
