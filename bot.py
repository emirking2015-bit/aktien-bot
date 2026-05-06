import os, json, requests, time, re
from datetime import datetime
from xml.etree import ElementTree
import pytz
import yfinance as yf

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

ALARM_SCHWELLE_PCT = 3.0
STATE_FILE = "kurse_state.json"
DE_TZ = pytz.timezone("Europe/Berlin")
US_TZ = pytz.timezone("America/New_York")

KRYPTO = {
    "BTC":  ("Bitcoin",     "bitcoin"),
    "ETH":  ("Ethereum",    "ethereum"),
    "SOL":  ("Solana",      "solana"),
    "HYPE": ("Hyperliquid", "hyperliquid"),
}

STOCKS = {
    "AMD":   "AMD",
    "INTC":  "Intel",
    "MU":    "Micron",
    "NOW":   "ServiceNow",
    "SNDK":  "SanDisk",
    "CRWV":  "CoreWeave",
    "CRCL":  "Circle",
    "NBIS":  "Nebius",
    "CGEH":  "CGEH",
    "HOOD":  "Robinhood",
    "RKLB":  "Rocket Lab",
    "BE":    "Bloom Energy",
    "IREN":  "Iris Energy",
    "WDC":   "Western Digital",
    "CAT":   "Caterpillar",
    "TEAM":  "Atlassian",
    "FLY":   "Firefly",
    "SMEGF": "Siemens Energy",
    "SSNLF": "Samsung",
    "GC=F":  "Gold",
    "SI=F":  "Silber",
}

GRUPPEN = {
    "KRYPTO":     ["BTC",  "ETH",  "SOL",  "HYPE"],
    "HALBLEITER": ["AMD",  "INTC", "MU",   "NOW",  "SNDK", "CRWV", "CRCL", "NBIS", "CGEH"],
    "AKTIEN":     ["HOOD", "RKLB", "BE",   "IREN", "WDC",  "CAT",  "TEAM", "FLY",  "SMEGF", "SSNLF"],
    "ROHSTOFFE":  ["GC=F", "SI=F"],
}

GRUPPEN_EMOJI = {
    "KRYPTO":     "\U0001fa99 KRYPTO",
    "HALBLEITER": "\U0001f4be HALBLEITER",
    "AKTIEN":     "\U0001f4c8 AKTIEN",
    "ROHSTOFFE":  "\U0001faa8 ROHSTOFFE",
}

RSS_FEEDS = [
    ("Maerkte",   "https://feeds.reuters.com/reuters/businessNews"),
    ("Maerkte",   "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
    ("Krypto",    "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Krypto",    "https://cointelegraph.com/rss"),
    ("Tech",      "https://feeds.reuters.com/reuters/technologyNews"),
    ("Aktien",    "https://finance.yahoo.com/rss/headline?s=AMD"),
    ("Aktien",    "https://finance.yahoo.com/rss/headline?s=HOOD"),
    ("Watchlist", "https://finance.yahoo.com/rss/headline?s=RKLB"),
    ("Watchlist", "https://finance.yahoo.com/rss/headline?s=CRWV"),
    ("Watchlist", "https://finance.yahoo.com/rss/headline?s=NBIS"),
]

RSS_EMOJI = {
    "Maerkte":   "\U0001f30d Maerkte",
    "Krypto":    "\u20bf Krypto",
    "Tech":      "\U0001f4be Tech",
    "Aktien":    "\U0001f4c8 Aktien",
    "Watchlist": "\U0001f680 Watchlist",
}


def eur_rate():
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=USD&to=EUR", timeout=8)
        if r.ok:
            return round(float(r.json()["rates"]["EUR"]), 4)
    except Exception as e:
        print("EUR frankfurter error: " + str(e))
    try:
        eurusd = float(yf.Ticker("EURUSD=X").fast_info.last_price)
        if eurusd > 0:
            return round(1.0 / eurusd, 4)
    except Exception as e:
        print("EUR yfinance error: " + str(e))
    return 0.91


def coingecko_kurse():
    ids = ",".join(cid for _, cid in KRYPTO.values())
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                         params={"ids": ids, "vs_currencies": "usd"}, timeout=15)
        if r.ok:
            data = r.json()
            return {s: round(float(data[cid]["usd"]), 6)
                    for s, (_, cid) in KRYPTO.items() if cid in data}
    except Exception as e:
        print("CoinGecko error: " + str(e))
    return {}


def yfinance_kurse():
    tickers = list(STOCKS.keys())
    result = {}
    try:
        data = yf.download(tickers, period="1d", interval="1m",
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
        print("yfinance batch error: " + str(e))
    for t in [x for x in tickers if x not in result]:
        try:
            p = yf.Ticker(t).fast_info.last_price
            if p and float(p) > 0:
                result[t] = round(float(p), 6)
            time.sleep(0.2)
        except Exception:
            pass
    return result


def alle_kurse():
    print("Fetching crypto...")
    kurse = coingecko_kurse()
    print("Got " + str(len(kurse)) + " crypto")
    print("Fetching stocks...")
    stocks = yfinance_kurse()
    print("Got " + str(len(stocks)) + " stocks")
    kurse.update(stocks)
    return kurse


def state_laden():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def state_speichern(kurse):
    with open(STATE_FILE, "w") as f:
        json.dump(kurse, f)


def rss_fetch(url):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if not r.ok:
            return []
        root = ElementTree.fromstring(r.content)
        titles = []
        for item in root.findall(".//item")[:3]:
            t = item.findtext("title", "").strip()
            t = re.sub(r"<[^>]+>", "", t)
            t = t.replace("&amp;", "&").replace("&#39;", "'")
            if t and len(t) > 15:
                titles.append(t)
        return titles
    except Exception:
        return []


def news_senden(now):
    jetzt = now.strftime("%d.%m.%Y  %H:%M Uhr")
    lines = [
        "\u2501" * 22,
        "\U0001f4f0  <b>MARKTNEWS</b>",
        "\U0001f550  " + jetzt,
        "\u2501" * 22,
        "",
    ]
    seen = set()
    current_label = None
    total = 0
    for label_key, url in RSS_FEEDS:
        neue = [t for t in rss_fetch(url) if t not in seen]
        if not neue:
            continue
        display = RSS_EMOJI.get(label_key, label_key)
        if label_key != current_label:
            if current_label is not None:
                lines.append("")
            lines.append("<b>" + display + "</b>")
            current_label = label_key
        for t in neue[:2]:
            seen.add(t)
            lines.append("  \u25b8 " + t)
            total += 1
    if total > 0:
        lines.append("")
        lines.append("\u2501" * 22)
        telegram_senden("\n".join(lines))
        print(str(total) + " news sent")
    else:
        print("No news received")


def fmt_usd(v):
    if v >= 10000:
        return "${:>11,.0f}".format(v)
    if v >= 100:
        return "${:>11,.2f}".format(v)
    if v >= 1:
        return "${:>11,.3f}".format(v)
    return "${:>11,.5f}".format(v)


def fmt_eur(v, rate):
    e = v * rate
    if e >= 10000:
        return "{:>9,.0f}\u20ac".format(e)
    if e >= 100:
        return "{:>9,.2f}\u20ac".format(e)
    if e >= 1:
        return "{:>9,.3f}\u20ac".format(e)
    return "{:>9,.5f}\u20ac".format(e)


def pfeil_diff(sym, kurs, letzter):
    ref = letzter.get(sym)
    if not ref or ref <= 0:
        return "\u26aa", "   -"
    d = (kurs - ref) / ref * 100
    if d >= 1.0:
        return "\U0001f7e2", "+{:.1f}%".format(d)
    elif d >= 0.1:
        return "\U0001f7e1", "+{:.1f}%".format(d)
    elif d <= -1.0:
        return "\U0001f534", "{:.1f}%".format(d)
    elif d <= -0.1:
        return "\U0001f7e0", "{:.1f}%".format(d)
    return "\u26aa", "0.0%"


def get_name(sym):
    if sym in KRYPTO:
        return KRYPTO[sym][0]
    return STOCKS.get(sym, sym)


def bericht_erstellen(kurse, rate, titel, letzter):
    now = datetime.now(DE_TZ)
    jetzt = now.strftime("%d.%m.  %H:%M Uhr")
    sep = "\u2501" * 22
    lines = [
        "<b>" + sep + "</b>",
        "<b>" + titel + "</b>",
        "\U0001f550 " + jetzt + "  |  \U0001f4b1 1$ = {:.4f}\u20ac".format(rate),
        "<b>" + sep + "</b>",
        "",
    ]
    for gruppe, syms in GRUPPEN.items():
        label = GRUPPEN_EMOJI.get(gruppe, gruppe)
        lines.append("<b>" + label + "</b>")
        for sym in syms:
            k = kurse.get(sym)
            name = get_name(sym)
            if k is None:
                lines.append("  \u26a0\ufe0f <i>" + name + "</i>")
                continue
            emoji, diff = pfeil_diff(sym, k, letzter)
            u = fmt_usd(k)
            e = fmt_eur(k, rate)
            lines.append("  " + emoji + " <b>" + name + "</b>")
            lines.append("     <code>" + u + "  " + e + "  " + diff + "</code>")
        lines.append("")
    lines.append(sep)
    return "\n".join(lines).rstrip()


def telegram_senden(text):
    try:
        r = requests.post(
            "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
        if not r.ok:
            print("TG error " + str(r.status_code) + ": " + r.text[:100])
    except Exception as e:
        print("TG error: " + str(e))


def main():
    now    = datetime.now(DE_TZ)
    now_ny = datetime.now(US_TZ)
    print("=== " + now.strftime("%d.%m.%Y %H:%M") + " ===")

    letzter = state_laden()
    erster  = len(letzter) == 0
    rate    = eur_rate()
    kurse   = alle_kurse()
    print("Kurse: " + str(len(kurse)) + "  Rate: " + str(rate))

    if not erster:
        for sym, k_neu in kurse.items():
            k_alt = letzter.get(sym)
            if not k_alt or k_alt <= 0:
                continue
            diff = (k_neu - k_alt) / k_alt * 100
            if abs(diff) >= ALARM_SCHWELLE_PCT:
                name = get_name(sym)
                direction = "gestiegen" if diff > 0 else "gefallen"
                arrow = "\U0001f680" if diff > 0 else "\U0001f53b"
                msg = (arrow + " <b>ALARM - " + name + "</b>\n" +
                       "\u2501" * 14 + "\n" +
                       "<b>{:+.2f}%</b> ".format(diff) + direction + "\n" +
                       "\U0001f4b5 " + fmt_usd(k_alt).strip() + " \u2192 <b>" + fmt_usd(k_neu).strip() + "</b>\n" +
                       "\U0001f4b6 " + fmt_eur(k_alt, rate).strip() + " \u2192 <b>" + fmt_eur(k_neu, rate).strip() + "</b>\n" +
                       "\u23f0 " + now.strftime("%H:%M Uhr"))
                telegram_senden(msg)
                print("ALARM: " + sym + " {:.2f}%".format(diff))

    if erster:
        titel = "\U0001f4ca Startkurse"
    elif now_ny.weekday() < 5 and now_ny.hour == 9 and now_ny.minute < 30:
        titel = "\U0001f514 US-Boerse oeffnet"
    elif now.hour == 20 and now.minute < 15:
        titel = "\U0001f4c5 Tagesbericht"
    else:
        titel = "\U0001f4ca 15-Min Update"

    telegram_senden(bericht_erstellen(kurse, rate, titel, letzter))

    if now.hour in (8, 14, 20) and now.minute < 15:
        news_senden(now)

    state_speichern(kurse)
    print("=== Done ===")


if __name__ == "__main__":
    main()
