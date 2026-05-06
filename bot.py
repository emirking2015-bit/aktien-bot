import os, json, requests, time, re
from datetime import datetime
from xml.etree import ElementTree
import pytz
import yfinance as yf

TOKEN   = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
ALARM_PCT  = 3.0
STATE_FILE = "state.json"
DE_TZ = pytz.timezone("Europe/Berlin")
US_TZ = pytz.timezone("America/New_York")

E_GREEN = "🟢"
E_YELL  = "🟡"
E_ORG   = "🟠"
E_RED   = "🔴"
E_GREY  = "⚪"
E_WARN  = "⚠️"
E_UP    = "🚀"
E_DOWN  = "🔻"
E_USD   = "💵"
E_EUR   = "💶"
E_CLK   = "🕐"
E_FX    = "💱"
E_NEWS  = "📰"
E_BELL  = "🔔"
E_CAL   = "📅"
E_SEP   = "━"
E_ARR   = "→"
E_DOT   = "▸"
E_BTC   = "🪙"
E_CHIP  = "💾"
E_CHART = "📈"
E_ROCK  = "🪨"

KRYPTO = {
    "BTC":  ("Bitcoin",     "bitcoin"),
    "ETH":  ("Ethereum",    "ethereum"),
    "SOL":  ("Solana",      "solana"),
    "HYPE": ("Hyperliquid", "hyperliquid"),
}

STOCKS = {
    "AMD":   "AMD",         "INTC":  "Intel",
    "MU":    "Micron",      "NOW":   "ServiceNow",
    "SNDK":  "SanDisk",     "CRWV":  "CoreWeave",
    "CRCL":  "Circle",      "NBIS":  "Nebius",
    "CGEH":  "CGEH",        "HOOD":  "Robinhood",
    "RKLB":  "Rocket Lab",  "BE":    "Bloom Energy",
    "IREN":  "Iris Energy", "WDC":   "Western Digital",
    "CAT":   "Caterpillar", "TEAM":  "Atlassian",
    "FLY":   "Firefly",     "SMEGF": "Siemens Energy",
    "SSNLF": "Samsung",     "GC=F":  "Gold",
    "SI=F":  "Silber",
}

GRUPPEN = [
    (E_BTC  + " KRYPTO",     ["BTC","ETH","SOL","HYPE"]),
    (E_CHIP + " HALBLEITER", ["AMD","INTC","MU","NOW","SNDK","CRWV","CRCL","NBIS","CGEH"]),
    (E_CHART+ " AKTIEN",     ["HOOD","RKLB","BE","IREN","WDC","CAT","TEAM","FLY","SMEGF","SSNLF"]),
    (E_ROCK + " ROHSTOFFE",  ["GC=F","SI=F"]),
]

RSS_FEEDS = [
    ("🌍 Maerkte",   "https://feeds.reuters.com/reuters/businessNews"),
    ("🌍 Maerkte",   "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
    ("₿ Krypto",        "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("₿ Krypto",        "https://cointelegraph.com/rss"),
    ("💾 Tech",      "https://feeds.reuters.com/reuters/technologyNews"),
    ("📈 Aktien",    "https://finance.yahoo.com/rss/headline?s=AMD"),
    ("📈 Aktien",    "https://finance.yahoo.com/rss/headline?s=HOOD"),
    ("🚀 Watchlist", "https://finance.yahoo.com/rss/headline?s=RKLB"),
    ("🚀 Watchlist", "https://finance.yahoo.com/rss/headline?s=CRWV"),
]


# ── EUR/USD ──────────────────────────────────
def eur_rate():
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=USD&to=EUR", timeout=8)
        if r.ok: return round(float(r.json()["rates"]["EUR"]), 4)
    except Exception: pass
    try:
        v = float(yf.Ticker("EURUSD=X").fast_info.last_price)
        if v > 0: return round(1.0 / v, 4)
    except Exception: pass
    return 0.91


# ── Prices with daily change ─────────────────
# Returns {sym: {"price": float, "pct": float}}
# pct = (current - prevClose) / prevClose * 100  <- same as Yahoo/Google Finance
def crypto_data():
    ids = ",".join(cid for _, cid in KRYPTO.values())
    result = {}
    try:
        # price + 24h change from CoinGecko
        r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                         params={"ids": ids, "vs_currencies": "usd",
                                 "include_24hr_change": "true"}, timeout=15)
        if r.ok:
            d = r.json()
            for sym, (_, cid) in KRYPTO.items():
                if cid not in d: continue
                price = float(d[cid].get("usd", 0))
                pct   = float(d[cid].get("usd_24h_change", 0))
                if price > 0:
                    result[sym] = {"price": round(price, 6), "pct": round(pct, 2)}
    except Exception as e:
        print("CoinGecko:", e)
    return result


def stock_data():
    tickers = list(STOCKS.keys())
    result = {}
    try:
        # yf.download gibt OHLCV — wir brauchen prevClose separat
        # Besser: Ticker.fast_info hat regularMarketPrice + previousClose
        for t in tickers:
            try:
                fi = yf.Ticker(t).fast_info
                price = fi.last_price
                prev  = fi.previous_close
                if price and prev and float(price) > 0 and float(prev) > 0:
                    pct = (float(price) - float(prev)) / float(prev) * 100
                    result[t] = {"price": round(float(price), 6), "pct": round(pct, 2)}
                time.sleep(0.15)
            except Exception as e:
                print("yf", t, e)
    except Exception as e:
        print("stock_data:", e)
    return result


def all_data():
    print("Fetching crypto...")
    data = crypto_data()
    print(" Got", len(data), "/", len(KRYPTO))
    print("Fetching stocks...")
    s = stock_data()
    print(" Got", len(s), "/", len(STOCKS))
    data.update(s)
    return data


# ── State (only for alarm logic) ─────────────
def load_state():
    try:
        with open(STATE_FILE) as f: return json.load(f)
    except Exception: return {}


def save_state(d):
    with open(STATE_FILE, "w") as f: json.dump(d, f)


# ── Formatting ───────────────────────────────
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


def day_arrow(pct):
    """Farb-Emoji basierend auf Tagesveraenderung."""
    if pct is None: return E_GREY, "  -"
    if pct >= 3.0:  return E_GREEN, "+{:.2f}%".format(pct)
    if pct >= 0.1:  return E_YELL,  "+{:.2f}%".format(pct)
    if pct <= -3.0: return E_RED,   "{:.2f}%".format(pct)
    if pct <= -0.1: return E_ORG,   "{:.2f}%".format(pct)
    return E_GREY, "{:.2f}%".format(pct)


def name_of(sym):
    if sym in KRYPTO: return KRYPTO[sym][0]
    return STOCKS.get(sym, sym)


def build_report(data, rate, title):
    now = datetime.now(DE_TZ)
    sep = E_SEP * 22
    lines = [
        "<b>" + sep + "</b>",
        E_CHART + "  <b>" + title + "</b>",
        E_CLK + "  " + now.strftime("%d.%m.%Y  %H:%M Uhr"),
        E_FX  + "  <code>1 USD = " + "{:.4f}".format(rate) + " €</code>",
        "<b>" + sep + "</b>",
        "",
    ]
    for grp, syms in GRUPPEN:
        lines.append("<b>" + grp + "</b>")
        for sym in syms:
            nm = name_of(sym)
            entry = data.get(sym)
            if entry is None:
                lines.append("  " + E_WARN + "  <i>" + nm + "</i>")
                continue
            p   = entry["price"]
            pct = entry.get("pct")
            ico, diff = day_arrow(pct)
            usd_str = fmt_usd(p)
            eur_str = fmt_eur(p, rate)
            lines.append("  " + ico + "  <b>" + nm + "</b>")
            lines.append("       <code>" + usd_str.ljust(13) + eur_str.ljust(12) + diff + "</code>")
        lines.append("")
    lines.append("<b>" + sep + "</b>")
    return chr(10).join(lines)


# ── News ─────────────────────────────────────
def rss_fetch(url):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if not r.ok: return []
        root = ElementTree.fromstring(r.content)
        out = []
        for item in root.findall(".//item")[:3]:
            t = item.findtext("title", "").strip()
            t = re.sub(r"<[^>]+>", "", t)
            t = t.replace("&amp;","&").replace("&#39;",chr(39)).replace("&quot;",chr(34))
            if len(t) > 15: out.append(t)
        return out
    except Exception: return []


def build_news():
    now = datetime.now(DE_TZ)
    sep = E_SEP * 22
    lines = [sep, E_NEWS + "  <b>MARKTNEWS</b>",
             E_CLK + "  " + now.strftime("%d.%m.%Y  %H:%M Uhr"), sep, ""]
    seen, cur, count = set(), None, 0
    for label, url in RSS_FEEDS:
        neue = [t for t in rss_fetch(url) if t not in seen]
        if not neue: continue
        if label != cur:
            if cur: lines.append("")
            lines.append("<b>" + label + "</b>")
            cur = label
        for t in neue[:2]:
            seen.add(t)
            lines.append("  " + E_DOT + "  " + t)
            count += 1
    if count == 0:
        lines.append("  <i>Keine News verfuegbar</i>")
    lines += ["", sep]
    return chr(10).join(lines)


# ── Telegram ─────────────────────────────────
def send(text):
    try:
        r = requests.post(
            "https://api.telegram.org/bot" + TOKEN + "/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
        if not r.ok: print("TG:", r.status_code, r.text[:80])
    except Exception as e:
        print("TG error:", e)


# ── Main ─────────────────────────────────────
def main():
    now    = datetime.now(DE_TZ)
    now_ny = datetime.now(US_TZ)
    print("===", now.strftime("%d.%m.%Y %H:%M"), "===")

    rate = eur_rate()
    data = all_data()
    print("Got", len(data), "entries, rate:", rate)

    # Alarm: Kurssprung zwischen zwei 15-Min-Checks
    state = load_state()
    for sym, entry in data.items():
        p_new = entry["price"]
        p_old = state.get(sym)
        if not p_old or float(p_old) <= 0: continue
        diff = (p_new - float(p_old)) / float(p_old) * 100
        if abs(diff) >= ALARM_PCT:
            nm  = name_of(sym)
            ico = E_UP if diff > 0 else E_DOWN
            dir = "gestiegen" if diff > 0 else "gefallen"
            sep = E_SEP * 16
            pct = entry.get("pct")
            tag = " (Heute: " + "{:+.2f}%".format(pct) + ")" if pct else ""
            msg = chr(10).join([
                ico + "  <b>ALARM - " + nm + "</b>",
                sep,
                "<b>" + "{:+.2f}%".format(diff) + "</b>  in 15 Min " + dir + tag,
                E_USD + "  " + fmt_usd(float(p_old)) + "  " + E_ARR + "  <b>" + fmt_usd(p_new) + "</b>",
                E_EUR + "  " + fmt_eur(float(p_old), rate) + "  " + E_ARR + "  <b>" + fmt_eur(p_new, rate) + "</b>",
            ])
            send(msg)
            print("ALARM:", sym, "{:+.2f}%".format(diff))

    # Titel
    if now_ny.weekday() < 5 and now_ny.hour == 9 and now_ny.minute < 30:
        title = E_BELL + " US-Boerse oeffnet"
    elif now.hour == 20 and now.minute < 15:
        title = E_CAL + " Tagesbericht"
    else:
        title = "📊 15-Min Update"

    send(build_report(data, rate, title))

    # News alle 6h
    if now.hour in (8, 14, 20) and now.minute < 15:
        send(build_news())

    # Preise fuer naechsten Alarm-Check speichern
    new_state = {sym: entry["price"] for sym, entry in data.items()}
    save_state(new_state)
    print("=== Done ===")


if __name__ == "__main__":
    main()
