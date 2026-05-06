import os, json, requests, time, re
from datetime import datetime
from xml.etree import ElementTree
import pytz
import yfinance as yf

TOKEN      = os.environ["TELEGRAM_TOKEN"]
CHAT_ID    = os.environ["TELEGRAM_CHAT_ID"]
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
E_BRAIN = "🧠"
E_FIRE  = "🔥"
E_BUY   = "💰"
E_SHORT = "🚨"
E_NEUTR = "⏸️"
E_STAR  = "⭐"

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
    "SI=F":  "Silber",      "BZ=F":  "Brent Oil",
}

TOP_MOVER_TICKERS = [
    "NVDA","TSLA","AMZN","MSFT","AAPL","META","GOOGL",
    "PLTR","MSTR","COIN","SMCI","ARM","AVGO","TSM",
    "IONQ","RGTI","OKLO","NNE","JOBY","LUNR","KULR",
    "MARA","RIOT","HUT","WULF","CORZ","CIFR","BTBT",
]

GRUPPEN = [
    (E_BTC  + " KRYPTO",     ["BTC","ETH","SOL","HYPE"]),
    (E_CHIP + " HALBLEITER", ["AMD","INTC","MU","NOW","SNDK","CRWV","CRCL","NBIS","CGEH"]),
    (E_CHART+ " AKTIEN",     ["HOOD","RKLB","BE","IREN","WDC","CAT","TEAM","FLY","SMEGF","SSNLF"]),
    (E_ROCK + " ROHSTOFFE",  ["GC=F","SI=F","BZ=F"]),
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


def crypto_data():
    ids = ",".join(cid for _, cid in KRYPTO.values())
    result = {}
    try:
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
                    result[sym] = {"price": round(price,6), "pct": round(pct,2)}
    except Exception as e:
        print("CoinGecko:", e)
    return result


def fetch_ticker_full(t):
    """Holt Preis, prev_close, 52w-high/low, avg_volume fuer Analyse."""
    try:
        tk = yf.Ticker(t)
        fi = tk.fast_info
        price = fi.last_price
        prev  = fi.previous_close
        if not price or not prev or float(price) <= 0: return None
        price = float(price)
        prev  = float(prev)
        pct   = (price - prev) / prev * 100
        result = {"price": round(price,6), "pct": round(pct,2)}
        # Zusatz-Daten fuer Analyse
        try:
            result["week52_high"] = float(fi.year_high) if fi.year_high else None
            result["week52_low"]  = float(fi.year_low)  if fi.year_low  else None
        except Exception: pass
        return result
    except Exception: return None


def stock_data():
    result = {}
    for t in list(STOCKS.keys()):
        d = fetch_ticker_full(t)
        if d: result[t] = d
        time.sleep(0.15)
    return result


def top_movers_data():
    result = {}
    for t in TOP_MOVER_TICKERS:
        d = fetch_ticker_full(t)
        if d: result[t] = d
        time.sleep(0.1)
    return result


def all_data():
    print("Fetching crypto...")
    data = crypto_data()
    print("Fetching stocks...")
    data.update(stock_data())
    print("Got", len(data), "prices")
    return data


def load_state():
    try:
        with open(STATE_FILE) as f: return json.load(f)
    except Exception: return {}

def save_state(d):
    with open(STATE_FILE, "w") as f: json.dump(d, f)


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
            nm    = name_of(sym)
            entry = data.get(sym)
            if entry is None:
                lines.append("  " + E_WARN + "  <i>" + nm + "</i>")
                continue
            p   = entry["price"]
            pct = entry.get("pct")
            ico, diff = day_arrow(pct)
            lines.append("  " + ico + "  <b>" + nm + "</b>")
            lines.append("       <code>" + fmt_usd(p).ljust(13) + fmt_eur(p,rate).ljust(12) + diff + "</code>")
        lines.append("")
    lines.append("<b>" + sep + "</b>")
    return chr(10).join(lines)


def build_top_movers(movers, rate):
    if not movers: return ""
    items = [(s, d["price"], d.get("pct",0)) for s,d in movers.items() if d.get("pct") is not None]
    items.sort(key=lambda x: x[2], reverse=True)
    gainers = items[:5]
    losers  = items[-5:][::-1]
    sep = E_SEP * 22
    lines = ["<b>" + sep + "</b>", E_FIRE + "  <b>TOP MOVER</b>", ""]
    lines.append(E_GREEN + "  <b>GAINER</b>")
    for sym, price, pct in gainers:
        lines.append("  " + E_GREEN + "  <b>" + sym + "</b>  <code>" + fmt_usd(price).ljust(11) + " +{:.2f}%".format(pct) + "</code>")
    lines.append("")
    lines.append(E_RED + "  <b>LOSER</b>")
    for sym, price, pct in losers:
        lines.append("  " + E_RED + "  <b>" + sym + "</b>  <code>" + fmt_usd(price).ljust(11) + " {:.2f}%".format(pct) + "</code>")
    lines += ["", "<b>" + sep + "</b>"]
    return chr(10).join(lines)


# ── Regelbasierte Analyse (kein API Key noetig) ──
def score_entry(sym, entry, all_entries):
    """Berechnet einen Score fuer Long/Short basierend auf Momentum + 52w-Position."""
    pct  = entry.get("pct", 0) or 0
    price = entry["price"]
    w52h = entry.get("week52_high")
    w52l = entry.get("week52_low")
    score = 0
    reasons = []
    # Tages-Momentum
    if pct >= 5:
        score += 3
        reasons.append("Starkes Tages-Momentum +" + "{:.1f}%".format(pct))
    elif pct >= 2:
        score += 2
        reasons.append("Positives Momentum +" + "{:.1f}%".format(pct))
    elif pct >= 0.5:
        score += 1
    elif pct <= -5:
        score -= 3
        reasons.append("Starker Abverkauf " + "{:.1f}%".format(pct))
    elif pct <= -2:
        score -= 2
        reasons.append("Schwacher Tag " + "{:.1f}%".format(pct))
    # 52-Wochen Position
    if w52h and w52l and w52h > w52l:
        rang = (price - w52l) / (w52h - w52l)
        if rang >= 0.9:
            score += 2
            reasons.append("Nahe 52W-Hoch (stark)")
        elif rang >= 0.7:
            score += 1
            reasons.append("Oberes 52W-Drittel")
        elif rang <= 0.2:
            score -= 2
            reasons.append("Nahe 52W-Tief (schwach)")
        elif rang <= 0.35:
            score -= 1
    return score, reasons


def build_analyse(all_entries, movers, rate):
    now = datetime.now(DE_TZ)
    sep = E_SEP * 22
    # Alle Titel zusammen bewerten
    combined = dict(all_entries)
    combined.update(movers)
    scored = []
    for sym, entry in combined.items():
        if entry.get("pct") is None: continue
        sc, reasons = score_entry(sym, entry, combined)
        name = name_of(sym)
        scored.append((sym, name, entry["price"], entry.get("pct",0), sc, reasons))
    scored.sort(key=lambda x: x[4], reverse=True)
    top_long  = [x for x in scored if x[4] >= 2][:4]
    top_short = [x for x in scored if x[4] <= -2][-3:][::-1]
    neutral   = [x for x in scored if -1 < x[4] < 2]
    lines = [
        "<b>" + sep + "</b>",
        E_BRAIN + "  <b>TAGESANALYSE</b>",
        E_CLK + "  " + now.strftime("%d.%m.%Y"),
        "<i>Regelbasiert | Kein Anlagerat</i>",
        "<b>" + sep + "</b>",
        "",
    ]
    # LONG
    lines.append(E_BUY + "  <b>LONG-CHANCEN</b>")
    if top_long:
        for sym, name, price, pct, sc, reasons in top_long:
            stars = E_STAR * min(sc, 5)
            lines.append("  " + E_GREEN + " <b>" + name + " (" + sym + ")</b>  " + stars)
            lines.append("    <code>" + fmt_usd(price) + "  " + "{:+.2f}%".format(pct) + "</code>")
            for r in reasons[:2]:
                lines.append("    " + E_DOT + " " + r)
            lines.append("")
    else:
        lines.append("  <i>Aktuell keine klaren Long-Signale</i>")
        lines.append("")
    # SHORT/MEIDEN
    lines.append(E_SHORT + "  <b>MEIDEN / SHORT</b>")
    if top_short:
        for sym, name, price, pct, sc, reasons in top_short:
            lines.append("  " + E_RED + " <b>" + name + " (" + sym + ")</b>")
            lines.append("    <code>" + fmt_usd(price) + "  " + "{:+.2f}%".format(pct) + "</code>")
            for r in reasons[:2]:
                lines.append("    " + E_DOT + " " + r)
            lines.append("")
    else:
        lines.append("  <i>Keine klaren Short-Signale</i>")
        lines.append("")
    # NEUTRAL
    if neutral:
        lines.append(E_NEUTR + "  <b>NEUTRAL / ABWARTEN</b>")
        for sym, name, price, pct, sc, reasons in neutral[:3]:
            lines.append("  " + E_GREY + " <b>" + name + "</b>  <code>" + "{:+.2f}%".format(pct) + "</code>")
        lines.append("")
    # Krypto separat
    krypto_items = [(s, d) for s, d in all_entries.items() if s in KRYPTO]
    if krypto_items:
        krypto_items.sort(key=lambda x: x[1].get("pct",0), reverse=True)
        lines.append(E_BTC + "  <b>KRYPTO HEUTE</b>")
        for sym, entry in krypto_items:
            pct = entry.get("pct", 0)
            ico, diff = day_arrow(pct)
            lines.append("  " + ico + " <b>" + KRYPTO[sym][0] + "</b>  <code>" + fmt_usd(entry["price"]) + "  " + diff + "</code>")
        lines.append("")
    lines.append("<b>" + sep + "</b>")
    return chr(10).join(lines)


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
    if count == 0: lines.append("  <i>Keine News verfuegbar</i>")
    lines += ["", sep]
    return chr(10).join(lines)


def send(text):
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        try:
            r = requests.post(
                "https://api.telegram.org/bot" + TOKEN + "/sendMessage",
                json={"chat_id": CHAT_ID, "text": chunk, "parse_mode": "HTML"},
                timeout=10
            )
            if not r.ok: print("TG:", r.status_code, r.text[:80])
        except Exception as e:
            print("TG error:", e)
        time.sleep(0.3)


def main():
    now    = datetime.now(DE_TZ)
    now_ny = datetime.now(US_TZ)
    print("===", now.strftime("%d.%m.%Y %H:%M"), "===")

    rate  = eur_rate()
    data  = all_data()
    state = load_state()

    # 15-Min Alarm
    for sym, entry in data.items():
        p_new = entry["price"]
        p_old = state.get(sym)
        if not p_old or float(p_old) <= 0: continue
        diff = (p_new - float(p_old)) / float(p_old) * 100
        if abs(diff) >= ALARM_PCT:
            nm  = name_of(sym)
            ico = E_UP if diff > 0 else E_DOWN
            dir = "gestiegen" if diff > 0 else "gefallen"
            pct = entry.get("pct")
            tag = " (Tag: " + "{:+.2f}%".format(pct) + ")" if pct else ""
            msg = chr(10).join([
                ico + "  <b>ALARM - " + nm + "</b>",
                E_SEP * 16,
                "<b>" + "{:+.2f}%".format(diff) + "</b> in 15 Min " + dir + tag,
                E_USD + "  " + fmt_usd(float(p_old)) + " " + E_ARR + " <b>" + fmt_usd(p_new) + "</b>",
                E_EUR + "  " + fmt_eur(float(p_old),rate) + " " + E_ARR + " <b>" + fmt_eur(p_new,rate) + "</b>",
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

    # Top Mover jede volle Stunde
    movers = {}
    if now.minute < 15:
        print("Fetching top movers...")
        movers = top_movers_data()
        msg = build_top_movers(movers, rate)
        if msg: send(msg)

    # News um 8, 14, 20 Uhr
    if now.hour in (8, 14, 20) and now.minute < 15:
        send(build_news())

    # Tagesanalyse taeglich um 9:00 Uhr
    if now.hour == 9 and now.minute < 15:
        print("Running analysis...")
        if not movers: movers = top_movers_data()
        send(build_analyse(data, movers, rate))
        print("Analysis sent")

    new_state = {sym: entry["price"] for sym, entry in data.items()}
    save_state(new_state)
    print("=== Done ===")


if __name__ == "__main__":
    main()
