import os, json, requests, time, re
from datetime import datetime, timedelta
from xml.etree import ElementTree
import pytz
import yfinance as yf

TOKEN      = os.environ["TELEGRAM_TOKEN"]
CHAT_ID    = os.environ["TELEGRAM_CHAT_ID"]
ALARM_PCT  = 3.0
STATE_FILE = "state.json"
DE_TZ = pytz.timezone("Europe/Berlin")
US_TZ = pytz.timezone("America/New_York")

# Emojis
E = {
    "green": "🟢", "yell": "🟡", "org": "🟠",
    "red": "🔴",   "grey": "⚪",      "warn": "⚠️",
    "up": "🚀",    "dn": "🔻",    "usd": "💵",
    "eur": "💶",   "clk": "🕐",   "fx": "💱",
    "news": "📰",  "bell": "🔔",  "cal": "📅",
    "sep": "━",       "arr": "→",        "dot": "▸",
    "btc": "🪙",   "chip": "💾",  "chart": "📈",
    "rock": "🪨",  "brain": "🧠", "fire": "🔥",
    "buy": "💰",   "short": "🚨", "neu": "⏸️",
    "star": "⭐",      "fear": "😨",  "greed": "🤑",
    "week": "📆",  "earn": "📋",  "oil": "🛢️",
    "pre": "🌅",   "moon": "🌙",  "sun": "☀️",
    "bank": "🏦",  "mag": "🔍",   "trophy": "🏆",
    "streak": "🔥","rsid": "📊",  "sec": "📜",
}

KRYPTO = {
    "BTC":  ("Bitcoin",     "bitcoin"),
    "ETH":  ("Ethereum",    "ethereum"),
    "SOL":  ("Solana",      "solana"),
    "HYPE": ("Hyperliquid", "hyperliquid"),
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
    "SI=F":  "Silber",       "BZ=F":  "Brent Oil",
}

GRUPPEN = [
    (E["btc"]  + " KRYPTO",     ["BTC","ETH","SOL","HYPE"]),
    (E["chip"] + " HALBLEITER", ["AMD","INTC","MU","NOW","SNDK","CRWV","CRCL","NBIS","CGEH"]),
    (E["chart"]+ " AKTIEN",     ["HOOD","RKLB","BE","IREN","WDC","CAT","TEAM","FLY","SMEGF","SSNLF"]),
    (E["rock"] + " ROHSTOFFE",  ["GC=F","SI=F","BZ=F"]),
]

# Grosse Caps - EU handelbar (MarketCap > 10 Mrd)
TOP_MOVER_TICKERS = [
    "NVDA","TSLA","AMZN","MSFT","AAPL","META","GOOGL","NFLX",
    "AVGO","TSM","QCOM","ARM","ASML","ORCL","CRM","NOW",
    "JPM","GS","V","MA","BAC","WFC",
    "XOM","CVX","NEE","AES",
    "LLY","JNJ","PFE","ABBV",
    "PLTR","COIN","SNOW","UBER","SPOT","SHOP",
]

# Sektor ETFs
SEKTOREN = {
    "XLK": "Technologie",  "XLF": "Finanzen",
    "XLE": "Energie",      "XLV": "Gesundheit",
    "XLI": "Industrie",    "XLC": "Kommunikation",
    "XLY": "Konsum",       "XLB": "Materialien",
    "XLRE":"Immobilien",   "XLU": "Versorger",
}

# Rohstoffe Dashboard
ROHSTOFFE_DASH = {
    "GC=F":  "Gold",       "SI=F":  "Silber",
    "BZ=F":  "Brent Oil",  "CL=F":  "WTI Oil",
    "NG=F":  "Erdgas",     "HG=F":  "Kupfer",
    "ZW=F":  "Weizen",     "ZC=F":  "Mais",
}

# Aschenbrenner Portfolio (13F Q4 2025, filed Feb 2026)
# Quelle: SEC 13F filing Situational Awareness LP
ASCHENBRENNER = {
    "BE":    ("Bloom Energy",      10_100_000,  875_000_000),
    "CRWV":  ("CoreWeave",          3_500_000,  450_000_000),
    "INTC":  ("Intel (Calls)",     20_200_000,  380_000_000),
    "LITE":  ("Lumentum",           5_200_000,  340_000_000),
    "CORZ":  ("Core Scientific",   28_000_000,  280_000_000),
    "IREN":  ("Iris Energy",       22_000_000,  180_000_000),
    "CIFR":  ("Cipher Mining",     35_000_000,   90_000_000),
    "WULF":  ("Terawulf",          25_000_000,   75_000_000),
    "HUT":   ("Hut 8",             12_000_000,   65_000_000),
}

RSS_FEEDS = [
    ("🌍 Maerkte",   "https://feeds.reuters.com/reuters/businessNews"),
    ("🌍 Maerkte",   "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
    ("₿ Krypto",        "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("₿ Krypto",        "https://cointelegraph.com/rss"),
    ("💾 Tech",      "https://feeds.reuters.com/reuters/technologyNews"),
    ("📈 Aktien",    "https://finance.yahoo.com/rss/headline?s=CRWV"),
    ("📈 Aktien",    "https://finance.yahoo.com/rss/headline?s=RKLB"),
    ("🚀 Watchlist", "https://finance.yahoo.com/rss/headline?s=IREN"),
]

# Zinsentscheid Termine 2026 (Fed + EZB)
FED_DATES = ["2026-01-29","2026-03-19","2026-05-07","2026-06-18",
             "2026-07-30","2026-09-17","2026-11-05","2026-12-17"]
EZB_DATES = ["2026-01-30","2026-03-06","2026-04-17","2026-06-05",
             "2026-07-24","2026-09-11","2026-10-29","2026-12-17"]


# ══════════════════════════════════════════
#  DATEN ABRUFEN
# ══════════════════════════════════════════

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
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                         params={"ids": ids, "vs_currencies": "usd",
                                 "include_24hr_change": "true"}, timeout=15)
        if r.ok:
            d = r.json()
            return {s: {"price": round(float(d[cid]["usd"]),6),
                        "pct": round(float(d[cid].get("usd_24h_change",0)),2)}
                    for s,(_, cid) in KRYPTO.items() if cid in d and d[cid].get("usd",0) > 0}
    except Exception as e: print("CoinGecko:", e)
    return {}


def fetch_yf(ticker):
    try:
        fi = yf.Ticker(ticker).fast_info
        price = float(fi.last_price)
        prev  = float(fi.previous_close)
        if price > 0 and prev > 0:
            return {"price": round(price,6), "pct": round((price-prev)/prev*100,2),
                    "prev": round(prev,6)}
    except Exception: pass
    return None


def stock_data():
    result = {}
    for t in list(STOCKS.keys()):
        d = fetch_yf(t)
        if d: result[t] = d
        time.sleep(0.15)
    return result


def all_data():
    data = crypto_data()
    data.update(stock_data())
    return data


def top_movers_data():
    result = {}
    for t in TOP_MOVER_TICKERS:
        d = fetch_yf(t)
        if d: result[t] = d
        time.sleep(0.1)
    return result


def sektor_data():
    result = {}
    for ticker, name in SEKTOREN.items():
        d = fetch_yf(ticker)
        if d: result[ticker] = {"name": name, "pct": d["pct"]}
        time.sleep(0.1)
    return result


def rohstoff_data():
    result = {}
    for ticker, name in ROHSTOFFE_DASH.items():
        d = fetch_yf(ticker)
        if d: result[ticker] = {"name": name, "price": d["price"], "pct": d["pct"]}
        time.sleep(0.1)
    return result


def fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=8)
        if r.ok:
            item = r.json()["data"][0]
            val  = int(item["value"])
            cls  = item["value_classification"]
            return val, cls
    except Exception: pass
    return None, None


def reddit_sentiment():
    try:
        headers = {"User-Agent": "Mozilla/5.0 StockBot/1.0"}
        r = requests.get("https://www.reddit.com/r/wallstreetbets/hot.json?limit=25",
                         headers=headers, timeout=10)
        if not r.ok: return []
        posts = r.json()["data"]["children"]
        ticker_count = {}
        pat = re.compile(r"\b([A-Z]{2,5})\b")
        skip = {"AI","EPS","CEO","IPO","GDP","SEC","FED","ETF","SPY","QQQ",
                "IMO","YOLO","DD","OTM","ITM","ATH","ATM","WSB","TLDR",
                "USA","USD","EUR","THE","FOR","ARE","NOT","YOU","BUT","ITS"}
        for post in posts:
            title = post["data"].get("title","")
            for m in pat.findall(title):
                if m not in skip and len(m) >= 2:
                    ticker_count[m] = ticker_count.get(m, 0) + 1
        sorted_tickers = sorted(ticker_count.items(), key=lambda x: x[1], reverse=True)
        return sorted_tickers[:10]
    except Exception as e:
        print("Reddit:", e)
        return []


def insider_trades():
    try:
        r = requests.get(
            "http://openinsider.com/screener?s=&o=&pl=&ph=&ls=&lh=&fd=1&td=&tdr=&fdlyl=&fdlyh=&daysago=1&xp=1&xs=1&vl=&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999&grp=0&nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&sortcol=0&cnt=10&Action=1",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10
        )
        if not r.ok: return []
        rows = re.findall(r"<tr[^>]*>.*?</tr>", r.text, re.DOTALL)
        trades = []
        for row in rows[1:6]:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
            cells = [re.sub(r"<[^>]+>","",c).strip() for c in cells]
            if len(cells) >= 8:
                trades.append(cells)
        return trades
    except Exception as e:
        print("Insider:", e)
        return []


def earnings_this_week():
    now = datetime.now(DE_TZ)
    week_end = now + timedelta(days=7)
    upcoming = []
    for ticker in list(STOCKS.keys()) + list(KRYPTO.keys()):
        try:
            cal = yf.Ticker(ticker).calendar
            if cal is not None and not cal.empty:
                if hasattr(cal, "columns"):
                    for col in cal.columns:
                        val = cal[col].iloc[0] if len(cal) > 0 else None
                        if val and hasattr(val, "date"):
                            if now.date() <= val.date() <= week_end.date():
                                nm = STOCKS.get(ticker, ticker)
                                upcoming.append((ticker, nm, str(val.date())))
                                break
            time.sleep(0.1)
        except Exception:
            pass
    return upcoming


def wirtschaftskalender_heute():
    now = datetime.now(DE_TZ)
    today_str = now.strftime("%Y-%m-%d")
    events = []
    if today_str in FED_DATES:
        events.append(E["bank"] + " FED Zinsentscheid heute!")
    if today_str in EZB_DATES:
        events.append(E["bank"] + " EZB Zinsentscheid heute!")
    # Naechste Termine
    upcoming_fed = [d for d in FED_DATES if d > today_str]
    upcoming_ezb = [d for d in EZB_DATES if d > today_str]
    naechst = []
    if upcoming_fed:
        naechst.append("Fed: " + upcoming_fed[0])
    if upcoming_ezb:
        naechst.append("EZB: " + upcoming_ezb[0])
    return events, naechst


# ══════════════════════════════════════════
#  FORMATIERUNG
# ══════════════════════════════════════════

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
    if pct is None: return E["grey"], "  -"
    if pct >= 3.0:  return E["green"], "+{:.2f}%".format(pct)
    if pct >= 0.1:  return E["yell"],  "+{:.2f}%".format(pct)
    if pct <= -3.0: return E["red"],   "{:.2f}%".format(pct)
    if pct <= -0.1: return E["org"],   "{:.2f}%".format(pct)
    return E["grey"], "{:.2f}%".format(pct)

def name_of(sym):
    if sym in KRYPTO: return KRYPTO[sym][0]
    return STOCKS.get(sym, sym)

def sep_line():
    return E["sep"] * 22

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
        except Exception as e: print("TG:", e)
        time.sleep(0.3)


# ══════════════════════════════════════════
#  STATE
# ══════════════════════════════════════════

def load_state():
    try:
        with open(STATE_FILE) as f: return json.load(f)
    except Exception: return {}

def save_state(d):
    with open(STATE_FILE, "w") as f: json.dump(d, f)

def rss_fetch(url):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if not r.ok: return []
        root = ElementTree.fromstring(r.content)
        out = []
        for item in root.findall(".//item")[:3]:
            t = item.findtext("title","").strip()
            t = re.sub(r"<[^>]+>","",t).replace("&amp;","&").replace("&#39;",chr(39))
            if len(t) > 15: out.append(t)
        return out
    except Exception: return []


# ══════════════════════════════════════════
#  NACHRICHTEN BAUEN
# ══════════════════════════════════════════

def build_kursbericht(data, rate, title):
    now = datetime.now(DE_TZ)
    sep = sep_line()
    lines = [
        "<b>" + sep + "</b>",
        E["chart"] + "  <b>" + title + "</b>",
        E["clk"] + "  " + now.strftime("%d.%m.%Y  %H:%M Uhr"),
        E["fx"]  + "  <code>1 USD = " + "{:.4f}".format(rate) + " €</code>",
        "<b>" + sep + "</b>", "",
    ]
    for grp, syms in GRUPPEN:
        lines.append("<b>" + grp + "</b>")
        for sym in syms:
            entry = data.get(sym)
            nm = name_of(sym)
            if entry is None:
                lines.append("  " + E["warn"] + "  <i>" + nm + "</i>")
                continue
            p = entry["price"]
            ico, diff = day_arrow(entry.get("pct"))
            lines.append("  " + ico + "  <b>" + nm + "</b>")
            lines.append("       <code>" + fmt_usd(p).ljust(13) + fmt_eur(p,rate).ljust(12) + diff + "</code>")
        lines.append("")
    lines.append("<b>" + sep + "</b>")
    return chr(10).join(lines)


def build_fear_greed(val, cls):
    if val is None: return ""
    sep = sep_line()
    if val >= 75:   icon = E["greed"]; label = "Extreme Gier"
    elif val >= 55: icon = E["greed"]; label = "Gier"
    elif val >= 45: icon = E["grey"];  label = "Neutral"
    elif val >= 25: icon = E["fear"];  label = "Angst"
    else:           icon = E["fear"];  label = "Extreme Angst"
    bar_filled = int(val / 5)
    bar = "█" * bar_filled + "░" * (20 - bar_filled)
    lines = [
        sep, icon + "  <b>FEAR & GREED INDEX</b>", "",
        "<code>[" + bar + "]</code>",
        "<b>" + str(val) + "/100</b>  " + label,
        "", sep,
    ]
    return chr(10).join(lines)


def build_rohstoff_dashboard(rohstoffe, rate):
    sep = sep_line()
    lines = [sep, E["oil"] + "  <b>ROHSTOFF-DASHBOARD</b>", ""]
    for ticker, info in rohstoffe.items():
        ico, diff = day_arrow(info["pct"])
        p = info["price"]
        lines.append("  " + ico + "  <b>" + info["name"] + "</b>")
        lines.append("       <code>" + fmt_usd(p).ljust(12) + fmt_eur(p,rate).ljust(11) + diff + "</code>")
    lines += ["", sep]
    return chr(10).join(lines)


def build_sektor_heatmap(sektoren):
    sep = sep_line()
    sorted_s = sorted(sektoren.items(), key=lambda x: x[1]["pct"], reverse=True)
    lines = [sep, E["chart"] + "  <b>SEKTOR-HEATMAP</b>", ""]
    for ticker, info in sorted_s:
        ico, diff = day_arrow(info["pct"])
        lines.append("  " + ico + "  <b>" + info["name"] + "</b>  <code>" + diff + "</code>")
    lines += ["", sep]
    return chr(10).join(lines)


def build_top_movers(movers, rate):
    items = [(s,d["price"],d.get("pct",0)) for s,d in movers.items() if d.get("pct") is not None]
    items.sort(key=lambda x: x[2], reverse=True)
    gainers = items[:6]
    losers  = items[-6:][::-1]
    sep = sep_line()
    lines = [sep, E["fire"] + "  <b>TOP MOVER (Markt)</b>", "",
             E["green"] + "  <b>GAINER</b>"]
    for sym, price, pct in gainers:
        lines.append("  " + E["green"] + "  <b>" + sym + "</b>  <code>" + fmt_usd(price).ljust(11) + " +{:.2f}%".format(pct) + "</code>")
    lines.append("")
    lines.append(E["red"] + "  <b>LOSER</b>")
    for sym, price, pct in losers:
        lines.append("  " + E["red"] + "  <b>" + sym + "</b>  <code>" + fmt_usd(price).ljust(11) + " {:.2f}%".format(pct) + "</code>")
    lines += ["", sep]
    return chr(10).join(lines)


def build_reddit_sentiment(tickers):
    sep = sep_line()
    lines = [sep, E["mag"] + "  <b>REDDIT WSB SENTIMENT</b>", ""]
    if not tickers:
        lines.append("  <i>Keine Daten verfuegbar</i>")
    else:
        for sym, count in tickers[:8]:
            bar = "█" * min(count * 2, 10)
            lines.append("  <b>" + sym.ljust(6) + "</b>  <code>" + bar + " " + str(count) + "x</code>")
    lines += ["", sep]
    return chr(10).join(lines)


def build_insider_trades(trades):
    sep = sep_line()
    lines = [sep, E["sec"] + "  <b>INSIDER TRADES (Heute)</b>", ""]
    if not trades:
        lines.append("  <i>Keine Insider-Kaeufe gemeldet</i>")
    else:
        for cells in trades[:5]:
            if len(cells) >= 6:
                lines.append("  " + E["dot"] + "  <b>" + cells[3] + "</b>  " + cells[4] + "  " + cells[5])
    lines += ["", sep]
    return chr(10).join(lines)


def build_trendanalyse(data):
    sep = sep_line()
    lines = [sep, E["rsid"] + "  <b>TREND & RELATIVE STAERKE</b>", ""]
    try:
        spy = fetch_yf("SPY")
        spy_pct = spy["pct"] if spy else 0
        lines.append("  S&P 500 heute: <code>" + "{:+.2f}%".format(spy_pct) + "</code>")
        lines.append("")
        outperformer = []
        underperformer = []
        for sym, entry in data.items():
            pct = entry.get("pct", 0)
            diff_vs_spy = pct - spy_pct
            nm = name_of(sym)
            if diff_vs_spy >= 2:
                outperformer.append((nm, sym, pct, diff_vs_spy))
            elif diff_vs_spy <= -2:
                underperformer.append((nm, sym, pct, diff_vs_spy))
        outperformer.sort(key=lambda x: x[3], reverse=True)
        underperformer.sort(key=lambda x: x[3])
        if outperformer:
            lines.append(E["green"] + "  <b>Schlaegt S&P500</b>")
            for nm, sym, pct, diff in outperformer[:5]:
                lines.append("  " + E["green"] + "  <b>" + nm + "</b>  <code>" + "{:+.2f}%".format(pct) + "  (+" + "{:.1f}% vs SPY)".format(diff) + "</code>")
            lines.append("")
        if underperformer:
            lines.append(E["red"] + "  <b>Schwaecher als S&P500</b>")
            for nm, sym, pct, diff in underperformer[:5]:
                lines.append("  " + E["red"] + "  <b>" + nm + "</b>  <code>" + "{:+.2f}%".format(pct) + "  ({:.1f}% vs SPY)".format(diff) + "</code>")
            lines.append("")
    except Exception as e:
        lines.append("  <i>Fehler: " + str(e) + "</i>")
    lines.append(sep)
    return chr(10).join(lines)


def build_korrelation_check(data):
    sep = sep_line()
    lines = [sep, E["brain"] + "  <b>KORRELATIONS-CHECK</b>", ""]
    btc_pct  = data.get("BTC", {}).get("pct", 0) or 0
    tech_avg = 0
    tech_syms = ["AMD","NVDA","INTC","MU","CRWV"]
    tech_vals = [data[s]["pct"] for s in tech_syms if s in data and data[s].get("pct") is not None]
    if tech_vals: tech_avg = sum(tech_vals) / len(tech_vals)
    if btc_pct <= -3 and tech_avg <= -3:
        lines.append("  " + E["warn"] + " <b>CRASH-SIGNAL!</b> BTC & Tech gleichzeitig stark im Minus")
        lines.append("  BTC: <code>" + "{:+.2f}%".format(btc_pct) + "</code>  |  Tech: <code>" + "{:+.2f}%".format(tech_avg) + "</code>")
    elif btc_pct >= 3 and tech_avg >= 3:
        lines.append("  " + E["fire"] + " <b>RISK-ON!</b> BTC & Tech gleichzeitig stark im Plus")
        lines.append("  BTC: <code>" + "{:+.2f}%".format(btc_pct) + "</code>  |  Tech: <code>" + "{:+.2f}%".format(tech_avg) + "</code>")
    else:
        lines.append("  " + E["neu"] + " Keine aussergewoehnliche Korrelation")
        lines.append("  BTC: <code>" + "{:+.2f}%".format(btc_pct) + "</code>  |  Tech: <code>" + "{:+.2f}%".format(tech_avg) + "</code>")
    lines += ["", sep]
    return chr(10).join(lines)


def build_aschenbrenner(rate):
    sep = sep_line()
    lines = [sep, "🧠  <b>ASCHENBRENNER PORTFOLIO</b>",
             "<i>Situational Awareness LP | 13F Q4 2025</i>", ""]
    total_now  = 0
    total_orig = 0
    for ticker, (name, shares, orig_val) in ASCHENBRENNER.items():
        d = fetch_yf(ticker)
        time.sleep(0.1)
        if d:
            cur_val = d["price"] * shares
            pnl     = cur_val - orig_val
            pnl_pct = (cur_val - orig_val) / orig_val * 100
            total_now  += cur_val
            total_orig += orig_val
            ico, diff = day_arrow(d.get("pct"))
            pnl_icon = E["green"] if pnl > 0 else E["red"]
            lines.append("  " + ico + "  <b>" + name + "</b>  <code>" + diff + "</code>")
            lines.append("       <code>Kurs: " + fmt_usd(d["price"]) + "  |  " + pnl_icon + " " + ("+" if pnl > 0 else "") + "${:,.0f}M  ({:+.1f}%)".format(pnl/1e6, pnl_pct) + "</code>")
        else:
            lines.append("  " + E["warn"] + "  <i>" + name + "</i>")
        lines.append("")
    if total_orig > 0:
        total_pnl = total_now - total_orig
        total_pct = total_pnl / total_orig * 100
        lines.append("<b>Portfolio Gesamt:</b>")
        lines.append("<code>Einstieg:  ${:,.0f}M".format(total_orig/1e6) + "</code>")
        lines.append("<code>Aktuell:   ${:,.0f}M".format(total_now/1e6) + "</code>")
        ico = E["green"] if total_pnl > 0 else E["red"]
        lines.append("<code>P&L:       " + ico + " " + ("+" if total_pnl > 0 else "") + "${:,.0f}M  ({:+.1f}%)".format(total_pnl/1e6, total_pct) + "</code>")
    lines += ["", "<i>Nur Long-Positionen aus 13F. Calls/Puts nicht enthalten.</i>", sep]
    return chr(10).join(lines)


def build_streak_trophy(data, state):
    sep = sep_line()
    lines = [sep, E["trophy"] + "  <b>TAGES-TROPHY & STREAKS</b>", ""]
    entries = [(name_of(s), s, d.get("pct",0)) for s,d in data.items() if d.get("pct") is not None]
    entries.sort(key=lambda x: x[2], reverse=True)
    if entries:
        best  = entries[0]
        worst = entries[-1]
        lines.append(E["trophy"] + "  <b>Heutiger Gewinner:</b>")
        lines.append("  " + E["green"] + "  <b>" + best[0] + "</b>  <code>+" + "{:.2f}%".format(best[2]) + "</code>")
        lines.append("")
        lines.append(E["dn"] + "  <b>Heutiger Verlierer:</b>")
        lines.append("  " + E["red"] + "  <b>" + worst[0] + "</b>  <code>" + "{:.2f}%".format(worst[2]) + "</code>")
        lines.append("")
    # Streak tracking
    today = datetime.now(DE_TZ).strftime("%Y-%m-%d")
    streaks = state.get("streaks", {})
    streak_lines = []
    for sym, d in data.items():
        pct = d.get("pct", 0)
        if pct is None: continue
        streak = streaks.get(sym, {"days": 0, "dir": "n", "last": ""})
        if streak["last"] == today:
            continue
        direction = "up" if pct > 0.1 else ("dn" if pct < -0.1 else "n")
        if direction == streak["dir"] and direction != "n":
            streak["days"] += 1
        else:
            streak["days"] = 1
            streak["dir"] = direction
        streak["last"] = today
        streaks[sym] = streak
        if streak["days"] >= 3:
            streak_lines.append((sym, streak["days"], direction))
    state["streaks"] = streaks
    if streak_lines:
        lines.append(E["streak"] + "  <b>AKTIVE STREAKS</b>")
        for sym, days, direction in sorted(streak_lines, key=lambda x: x[1], reverse=True):
            nm  = name_of(sym)
            ico = E["green"] if direction == "up" else E["red"]
            fir = E["fire"] if days >= 5 else ""
            lines.append("  " + ico + "  <b>" + nm + "</b>  " + str(days) + " Tage " + ("im Plus" if direction=="up" else "im Minus") + "  " + fir)
    lines += ["", sep]
    return chr(10).join(lines), state


def build_news():
    now = datetime.now(DE_TZ)
    sep = sep_line()
    lines = [sep, E["news"] + "  <b>MARKTNEWS</b>",
             E["clk"] + "  " + now.strftime("%d.%m.%Y  %H:%M Uhr"), sep, ""]
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
            lines.append("  " + E["dot"] + "  " + t)
            count += 1
    if count == 0: lines.append("  <i>Keine News verfuegbar</i>")
    lines += ["", sep]
    return chr(10).join(lines)


def build_wochen_recap(state):
    sep = sep_line()
    lines = [sep, E["week"] + "  <b>WOCHEN-RECAP</b>", ""]
    weekly = state.get("weekly_open", {})
    if not weekly:
        lines.append("  <i>Noch keine Wochendaten</i>")
    else:
        results = []
        for sym, open_price in weekly.items():
            d = fetch_yf(sym)
            time.sleep(0.05)
            if d and open_price > 0:
                pct = (d["price"] - open_price) / open_price * 100
                results.append((name_of(sym), sym, pct))
        results.sort(key=lambda x: x[2], reverse=True)
        lines.append(E["green"] + "  <b>BESTE WOCHE</b>")
        for nm, sym, pct in results[:5]:
            ico, diff = day_arrow(pct)
            lines.append("  " + ico + "  <b>" + nm + "</b>  <code>" + diff + "</code>")
        lines.append("")
        lines.append(E["red"] + "  <b>SCHLECHTESTE WOCHE</b>")
        for nm, sym, pct in results[-5:][::-1]:
            ico, diff = day_arrow(pct)
            lines.append("  " + ico + "  <b>" + nm + "</b>  <code>" + diff + "</code>")
    lines += ["", sep]
    return chr(10).join(lines)


def build_monats_recap(state):
    sep = sep_line()
    lines = [sep, E["cal"] + "  <b>MONATS-RECAP</b>", ""]
    monthly = state.get("monthly_open", {})
    if not monthly:
        lines.append("  <i>Noch keine Monatsdaten</i>")
    else:
        results = []
        for sym, open_price in monthly.items():
            d = fetch_yf(sym)
            time.sleep(0.05)
            if d and open_price > 0:
                pct = (d["price"] - open_price) / open_price * 100
                results.append((name_of(sym), sym, pct))
        results.sort(key=lambda x: x[2], reverse=True)
        for nm, sym, pct in results:
            ico, diff = day_arrow(pct)
            lines.append("  " + ico + "  <b>" + nm + "</b>  <code>" + diff + "</code>")
    lines += ["", sep]
    return chr(10).join(lines)


def build_earnings_reminder(upcoming):
    if not upcoming: return ""
    sep = sep_line()
    lines = [sep, E["earn"] + "  <b>EARNINGS DIESE WOCHE</b>", ""]
    for ticker, name, date_str in upcoming:
        lines.append("  " + E["bell"] + "  <b>" + name + "</b>  <code>" + date_str + "</code>")
    lines += ["", sep]
    return chr(10).join(lines)


def build_wirtschaftskalender(events, naechst):
    sep = sep_line()
    lines = [sep, E["bank"] + "  <b>WIRTSCHAFTSKALENDER</b>", ""]
    if events:
        for ev in events:
            lines.append("  " + E["warn"] + "  " + ev)
        lines.append("")
    if naechst:
        lines.append("  <b>Naechste Zinsentscheide:</b>")
        for n in naechst:
            lines.append("  " + E["dot"] + "  " + n)
    lines += ["", sep]
    return chr(10).join(lines)


def build_tagesanalyse(data, movers):
    sep = sep_line()
    combined = dict(data)
    combined.update(movers)
    scored = []
    for sym, entry in combined.items():
        pct = entry.get("pct", 0) or 0
        price = entry["price"]
        score = 0
        reasons = []
        if pct >= 5:   score += 3; reasons.append("Starkes Momentum +" + "{:.1f}%".format(pct))
        elif pct >= 2: score += 2; reasons.append("Positives Momentum +" + "{:.1f}%".format(pct))
        elif pct >= 0.5: score += 1
        elif pct <= -5:  score -= 3; reasons.append("Starker Abverkauf " + "{:.1f}%".format(pct))
        elif pct <= -2:  score -= 2; reasons.append("Schwacher Tag " + "{:.1f}%".format(pct))
        scored.append((sym, name_of(sym), price, pct, score, reasons))
    scored.sort(key=lambda x: x[4], reverse=True)
    top_long  = [x for x in scored if x[4] >= 2][:5]
    top_short = [x for x in scored if x[4] <= -2][-4:][::-1]
    lines = [sep, E["brain"] + "  <b>TAGESANALYSE</b>",
             E["clk"] + "  " + datetime.now(DE_TZ).strftime("%d.%m.%Y"),
             "<i>Regelbasiert | Kein Anlageberatung</i>",
             sep, ""]
    lines.append(E["buy"] + "  <b>LONG-CHANCEN</b>")
    if top_long:
        for sym, nm, price, pct, sc, reasons in top_long:
            stars = E["star"] * min(sc, 5)
            lines.append("  " + E["green"] + "  <b>" + nm + "</b>  " + stars)
            lines.append("    <code>" + fmt_usd(price) + "  " + "{:+.2f}%".format(pct) + "</code>")
            for r in reasons[:2]: lines.append("    " + E["dot"] + " " + r)
            lines.append("")
    else:
        lines.append("  <i>Keine klaren Long-Signale</i>"); lines.append("")
    lines.append(E["short"] + "  <b>MEIDEN / SHORT</b>")
    if top_short:
        for sym, nm, price, pct, sc, reasons in top_short:
            lines.append("  " + E["red"] + "  <b>" + nm + "</b>")
            lines.append("    <code>" + fmt_usd(price) + "  " + "{:+.2f}%".format(pct) + "</code>")
            for r in reasons[:2]: lines.append("    " + E["dot"] + " " + r)
            lines.append("")
    else:
        lines.append("  <i>Keine klaren Short-Signale</i>"); lines.append("")
    lines.append(sep)
    return chr(10).join(lines)


# ══════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════

def main():
    now    = datetime.now(DE_TZ)
    now_ny = datetime.now(US_TZ)
    h      = now.hour
    m      = now.minute
    wd     = now.weekday()  # 0=Mo, 6=So
    dom    = now.day        # day of month
    first15 = m < 15
    print("=== Bot", now.strftime("%d.%m.%Y %H:%M"), "===")

    state = load_state()
    rate  = eur_rate()
    data  = all_data()
    print("Prices:", len(data), "Rate:", rate)

    # ── 15-Min Alarm ─────────────────────────────
    for sym, entry in data.items():
        p_new = entry["price"]
        p_old = state.get(sym)
        if not p_old or float(p_old) <= 0: continue
        diff = (p_new - float(p_old)) / float(p_old) * 100
        if abs(diff) >= ALARM_PCT:
            nm  = name_of(sym)
            ico = E["up"] if diff > 0 else E["dn"]
            dir = "gestiegen" if diff > 0 else "gefallen"
            pct = entry.get("pct")
            tag = " (Tag: " + "{:+.2f}%".format(pct) + ")" if pct else ""
            msg = chr(10).join([
                ico + "  <b>ALARM - " + nm + "</b>",
                E["sep"] * 16,
                "<b>" + "{:+.2f}%".format(diff) + "</b> in 15 Min " + dir + tag,
                E["usd"] + "  " + fmt_usd(float(p_old)) + " " + E["arr"] + " <b>" + fmt_usd(p_new) + "</b>",
                E["eur"] + "  " + fmt_eur(float(p_old),rate) + " " + E["arr"] + " <b>" + fmt_eur(p_new,rate) + "</b>",
            ])
            send(msg)
            print("ALARM:", sym, "{:+.2f}%".format(diff))

    # ── Kursbericht Titel ─────────────────────────
    if h == 7 and first15:
        title = E["sun"] + " Guten Morgen"
    elif h == 20 and first15:
        title = E["cal"] + " Tagesbericht"
    elif now_ny.weekday() < 5 and now_ny.hour == 9 and now_ny.minute < 30:
        title = E["bell"] + " US-Boerse oeffnet"
    else:
        title = "📊 15-Min Update"

    send(build_kursbericht(data, rate, title))

    # ── 07:00 — Guten Morgen Paket ───────────────
    if h == 7 and first15:
        fg_val, fg_cls = fear_greed()
        if fg_val is not None:
            send(build_fear_greed(fg_val, fg_cls))
        roh = rohstoff_data()
        if roh: send(build_rohstoff_dashboard(roh, rate))
        wirt_events, wirt_naechst = wirtschaftskalender_heute()
        send(build_wirtschaftskalender(wirt_events, wirt_naechst))
        upcoming_earn = earnings_this_week()
        msg_earn = build_earnings_reminder(upcoming_earn)
        if msg_earn: send(msg_earn)

    # ── 09:00 — Tagesanalyse ─────────────────────
    if h == 9 and first15:
        print("Running analysis...")
        movers = top_movers_data()
        send(build_tagesanalyse(data, movers))
        send(build_trendanalyse(data))
        send(build_korrelation_check(data))

    # ── 14:30 — Pre-Market (30 Min vor US-Open) ──
    if h == 14 and 28 <= m <= 44 and now_ny.weekday() < 5:
        pre_lines = [sep_line(), E["pre"] + "  <b>PRE-MARKET (30 Min vor US-Open)</b>", ""]
        pre_syms  = ["NVDA","TSLA","AMZN","AAPL","META","MSFT","AMD","INTC","PLTR"]
        for sym in pre_syms:
            d = fetch_yf(sym)
            time.sleep(0.1)
            if d:
                ico, diff = day_arrow(d.get("pct"))
                pre_lines.append("  " + ico + "  <b>" + sym + "</b>  <code>" + fmt_usd(d["price"]).ljust(11) + diff + "</code>")
        pre_lines += ["", sep_line()]
        send(chr(10).join(pre_lines))

    # ── 15:30 — US-Open + Sektor-Heatmap ─────────
    if h == 15 and 28 <= m <= 44 and now_ny.weekday() < 5:
        sekt = sektor_data()
        if sekt: send(build_sektor_heatmap(sekt))

    # ── 17:00 — Reddit + Insider ─────────────────
    if h == 17 and first15:
        reddit = reddit_sentiment()
        send(build_reddit_sentiment(reddit))
        trades = insider_trades()
        send(build_insider_trades(trades))

    # ── 18:00 — Top Mover + Sektor ───────────────
    if h == 18 and first15:
        movers = top_movers_data()
        if movers: send(build_top_movers(movers, rate))
        sekt = sektor_data()
        if sekt: send(build_sektor_heatmap(sekt))

    # ── 20:00 — Tagesbericht Paket ───────────────
    if h == 20 and first15:
        send(build_news())
        send(build_korrelation_check(data))
        send(build_aschenbrenner(rate))

    # ── 22:15 — Streak + Trophy ──────────────────
    if h == 22 and 13 <= m <= 25:
        trophy_msg, state = build_streak_trophy(data, state)
        send(trophy_msg)

    # ── Sonntag 10:00 — Wochen-Recap ─────────────
    if wd == 6 and h == 10 and first15:
        send(build_wochen_recap(state))
        state["weekly_open"] = {sym: d["price"] for sym, d in data.items()}

    # ── 1. des Monats — Monats-Recap ─────────────
    if dom == 1 and h == 8 and first15:
        send(build_monats_recap(state))
        state["monthly_open"] = {sym: d["price"] for sym, d in data.items()}

    # Montag: Wochenanfang-Preise speichern
    if wd == 0 and h == 8 and first15:
        state["weekly_open"] = {sym: d["price"] for sym, d in data.items()}

    # Monatserster: Reset
    if dom == 1 and h == 0 and first15:
        state["monthly_open"] = {sym: d["price"] for sym, d in data.items()}

    # State speichern
    new_state = {sym: d["price"] for sym, d in data.items()}
    new_state["streaks"]      = state.get("streaks", {})
    new_state["weekly_open"]  = state.get("weekly_open", {})
    new_state["monthly_open"] = state.get("monthly_open", {})
    save_state(new_state)
    print("=== Done ===")


if __name__ == "__main__":
    main()
