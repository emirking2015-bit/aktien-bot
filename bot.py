import os
import json
import requests
import time
import re
from datetime import datetime
from xml.etree import ElementTree
import pytz
import yfinance as yf

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
ALARM_PCT = 3.0
STATE_FILE = "state.json"
DE_TZ = pytz.timezone("Europe/Berlin")
US_TZ = pytz.timezone("America/New_York")

KRYPTO = {
    "BTC":  ("Bitcoin",     "bitcoin"),
    "ETH":  ("Ethereum",    "ethereum"),
    "SOL":  ("Solana",      "solana"),
    "HYPE": ("Hyperliquid", "hyperliquid"),
}

STOCKS = {
    "AMD":   "AMD",   "INTC":  "Intel",
    "MU":    "Micron","NOW":   "ServiceNow",
    "SNDK":  "SanDisk","CRWV": "CoreWeave",
    "CRCL":  "Circle","NBIS":  "Nebius",
    "CGEH":  "CGEH",  "HOOD":  "Robinhood",
    "RKLB":  "Rocket Lab","BE": "Bloom Energy",
    "IREN":  "Iris Energy","WDC":"Western Digital",
    "CAT":   "Caterpillar","TEAM":"Atlassian",
    "FLY":   "Firefly","SMEGF":"Siemens Energy",
    "SSNLF": "Samsung","GC=F": "Gold","SI=F":"Silber",
}

G_KRYPTO =     '🪙 KRYPTO'
G_HALB  =      '💾 HALBLEITER'
G_AKTIEN =     '📈 AKTIEN'
G_ROHST =      '🪨 ROHSTOFFE'

GRUPPEN = [
    (G_KRYPTO,  ["BTC","ETH","SOL","HYPE"]),
    (G_HALB,    ["AMD","INTC","MU","NOW","SNDK","CRWV","CRCL","NBIS","CGEH"]),
    (G_AKTIEN,  ["HOOD","RKLB","BE","IREN","WDC","CAT","TEAM","FLY","SMEGF","SSNLF"]),
    (G_ROHST,   ["GC=F","SI=F"]),
]

LBL_MARKT =    '🌍 Maerkte'
LBL_KRYPTO =   '₿ Krypto'
LBL_TECH =     '💾 Tech'
LBL_AKTIEN =   '📈 Aktien'
LBL_WATCH =    '🚀 Watchlist'

RSS_FEEDS = [
    (LBL_MARKT,  "https://feeds.reuters.com/reuters/businessNews"),
    (LBL_MARKT,  "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
    (LBL_KRYPTO, "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    (LBL_KRYPTO, "https://cointelegraph.com/rss"),
    (LBL_TECH,   "https://feeds.reuters.com/reuters/technologyNews"),
    (LBL_AKTIEN, "https://finance.yahoo.com/rss/headline?s=AMD"),
    (LBL_AKTIEN, "https://finance.yahoo.com/rss/headline?s=HOOD"),
    (LBL_WATCH,  "https://finance.yahoo.com/rss/headline?s=RKLB"),
    (LBL_WATCH,  "https://finance.yahoo.com/rss/headline?s=CRWV"),
    (LBL_WATCH,  "https://finance.yahoo.com/rss/headline?s=NBIS"),
]


def eur_rate():
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=USD&to=EUR", timeout=8)
        if r.ok:
            return round(float(r.json()["rates"]["EUR"]), 4)
    except Exception as e:
        print("EUR error:", e)
    try:
        v = float(yf.Ticker("EURUSD=X").fast_info.last_price)
        if v > 0:
            return round(1.0 / v, 4)
    except Exception:
        pass
    return 0.91


def crypto_prices():
    ids = ",".join(cid for _, cid in KRYPTO.values())
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                         params={"ids": ids, "vs_currencies": "usd"}, timeout=15)
        if r.ok:
            data = r.json()
            return {s: round(float(data[cid]["usd"]), 6)
                    for s, (_, cid) in KRYPTO.items() if cid in data}
    except Exception as e:
        print("CoinGecko error:", e)
    return {}


def stock_prices():
    tickers = list(STOCKS.keys())
    result = {}
    try:
        data = yf.download(tickers, period="1d", interval="1m",
                           progress=False, threads=True, auto_adjust=True)
        closes = data["Close"]
        for t in tickers:
            try:
                last = closes[t].dropna().iloc[-1]
                if float(last) > 0:
                    result[t] = round(float(last), 6)
            except Exception:
                pass
    except Exception as e:
        print("yf batch error:", e)
    for t in [x for x in tickers if x not in result]:
        try:
            p = yf.Ticker(t).fast_info.last_price
            if p and float(p) > 0:
                result[t] = round(float(p), 6)
            time.sleep(0.2)
        except Exception:
            pass
    return result


def get_all_prices():
    print("Fetching crypto...")
    prices = crypto_prices()
    print("  Got", len(prices))
    print("Fetching stocks...")
    s = stock_prices()
    print("  Got", len(s))
    prices.update(s)
    return prices


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(prices):
    with open(STATE_FILE, "w") as f:
        json.dump(prices, f)


def rss_fetch(url):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if not r.ok:
            return []
        root = ElementTree.fromstring(r.content)
        out = []
        for item in root.findall(".//item")[:3]:
            t = item.findtext("title", "").strip()
            t = re.sub(r"<[^>]+>", "", t)
            t = t.replace("&amp;", "&").replace("&#39;", chr(39))
            if len(t) > 15:
                out.append(t)
        return out
    except Exception:
        return []


def send_news(now):
    sep = "━" * 20
    ICON_NEWS = "📰"
    ICON_TIME = "🕐"
    header = [sep, ICON_NEWS + " <b>MARKTNEWS</b>",
              ICON_TIME + " " + now.strftime("%d.%m.%Y %H:%M Uhr"), sep, ""]
    lines = list(header)
    seen = set()
    cur_lbl = None
    count = 0
    for label, url in RSS_FEEDS:
        neue = [t for t in rss_fetch(url) if t not in seen]
        if not neue:
            continue
        if label != cur_lbl:
            if cur_lbl:
                lines.append("")
            lines.append("<b>" + label + "</b>")
            cur_lbl = label
        for t in neue[:2]:
            seen.add(t)
            lines.append("  ▸ " + t)
            count += 1
    if count > 0:
        lines += ["", sep]
        send_telegram(chr(10).join(lines))
        print("News sent:", count)


def fmt_usd(v):
    if v >= 10000: return "${:,.0f}".format(v)
    if v >= 100:   return "${:,.2f}".format(v)
    if v >= 1:     return "${:,.3f}".format(v)
    return "${:,.5f}".format(v)


def fmt_eur(v, rate):
    e = v * rate
    if e >= 10000: return "{:,.0f}€".format(e)
    if e >= 100:   return "{:,.2f}€".format(e)
    if e >= 1:     return "{:,.3f}€".format(e)
    return "{:,.5f}€".format(e)


def get_arrow(sym, price, prev):
    ref = prev.get(sym)
    if not ref or ref <= 0: return "⚪", "  -"
    d = (price - ref) / ref * 100
    if d >= 1.0:  return "🟢", "+{:.1f}%".format(d)
    if d >= 0.1:  return "🟡", "+{:.1f}%".format(d)
    if d <= -1.0: return "🔴", "{:.1f}%".format(d)
    if d <= -0.1: return "🟠", "{:.1f}%".format(d)
    return "⚪", "0.0%"


def get_name(sym):
    if sym in KRYPTO: return KRYPTO[sym][0]
    return STOCKS.get(sym, sym)


def build_report(prices, rate, title, prev):
    now = datetime.now(DE_TZ)
    sep = "━" * 20
    ICON_CLK = "🕐"
    ICON_MON = "💱"
    ICON_WRN = "⚠"
    lines = [
        "<b>" + sep + "</b>",
        "<b>" + title + "</b>",
        ICON_CLK + " " + now.strftime("%d.%m.%Y %H:%M") + "  " + ICON_MON + " 1$=" + "{:.4f}€".format(rate),
        "<b>" + sep + "</b>",
        "",
    ]
    for group_name, syms in GRUPPEN:
        lines.append("<b>" + group_name + "</b>")
        for sym in syms:
            p = prices.get(sym)
            name = get_name(sym)
            if p is None:
                lines.append("  " + ICON_WRN + " <i>" + name + "</i>")
                continue
            arrow, diff = get_arrow(sym, p, prev)
            lines.append("  " + arrow + " <b>" + name + "</b>")
            lines.append("     <code>" + fmt_usd(p) + "  " + fmt_eur(p, rate) + "  " + diff + "</code>")
        lines.append("")
    lines.append(sep)
    return chr(10).join(lines)


def send_telegram(text):
    try:
        r = requests.post(
            "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
        if not r.ok:
            print("TG error:", r.status_code, r.text[:100])
    except Exception as e:
        print("TG error:", e)


def main():
    now = datetime.now(DE_TZ)
    now_ny = datetime.now(US_TZ)
    print("=== Bot", now.strftime("%d.%m.%Y %H:%M"), "===")
    prev = load_state()
    first_run = len(prev) == 0
    rate = eur_rate()
    prices = get_all_prices()
    print("Total:", len(prices), "Rate:", rate)
    if not first_run:
        ICON_UP = "🚀"
        ICON_DN = "🔻"
        ICON_USD = "💵"
        ICON_EUR = "💶"
        ICON_CLK = "⏰"
        ARR = "→"
        SEP = "━" * 14
        for sym, p_new in prices.items():
            p_old = prev.get(sym)
            if not p_old or p_old <= 0: continue
            diff = (p_new - p_old) / p_old * 100
            if abs(diff) >= ALARM_PCT:
                name = get_name(sym)
                icon = ICON_UP if diff > 0 else ICON_DN
                direction = "gestiegen" if diff > 0 else "gefallen"
                parts = [
                    icon + " <b>ALARM - " + name + "</b>",
                    SEP,
                    "<b>" + "{:+.2f}%".format(diff) + "</b> " + direction,
                    ICON_USD + " " + fmt_usd(p_old) + " " + ARR + " <b>" + fmt_usd(p_new) + "</b>",
                    ICON_EUR + " " + fmt_eur(p_old, rate) + " " + ARR + " <b>" + fmt_eur(p_new, rate) + "</b>",
                    ICON_CLK + " " + now.strftime("%H:%M Uhr"),
                ]
                send_telegram(chr(10).join(parts))
                print("ALARM:", sym, "{:+.2f}%".format(diff))
    TITLE_START = "📊 Startkurse"
    TITLE_US    = "🔔 US-Boerse oeffnet"
    TITLE_DAY   = "📅 Tagesbericht"
    TITLE_15    = "📊 15-Min Update"
    if first_run:
        title = TITLE_START
    elif now_ny.weekday() < 5 and now_ny.hour == 9 and now_ny.minute < 30:
        title = TITLE_US
    elif now.hour == 20 and now.minute < 15:
        title = TITLE_DAY
    else:
        title = TITLE_15
    send_telegram(build_report(prices, rate, title, prev))
    if now.hour in (8, 14, 20) and now.minute < 15:
        send_news(now)
    save_state(prices)
    print("=== Done ===")


if __name__ == "__main__":
    main()