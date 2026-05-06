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

# ─────────────────────────────────────────────
#  TICKER
# ─────────────────────────────────────────────

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

# ─────────────────────────────────────────────
#  EUR/USD — BUG FIX
#  EURUSD=X → wie viele USD für 1 EUR (z.B. 1.09)
#  Wir brauchen: wie viele EUR für 1 USD → 1 / 1.09 = 0.917
# ─────────────────────────────────────────────

def eur_rate() -> float:
    # Primär: frankfurter.app — gibt direkt EUR pro USD
    try:
        r = requests.get(
            "https://api.frankfurter.app/latest?from=USD&to=EUR",
            timeout=8
        )
        if r.ok:
            rate = float(r.json()["rates"]["EUR"])
            print(f"  EUR Rate (frankfurter): {rate}")
            return round(rate, 4)
    except Exception as e:
        print(f"  [EUR frankfurter] {e}")

    # Fallback: yfinance — MUSS invertiert werden!
    try:
        eurusd = float(yf.Ticker("EURUSD=X").fast_info.last_price)
        if eurusd > 0:
            rate = round(1.0 / eurusd, 4)  # ← Invertierung!
            print(f"  EUR Rate (yfinance, 1/{eurusd:.4f}): {rate}")
            return rate
    except Exception as e:
        print(f"  [EUR yfinance] {e}")

    return 0.91

# ─────────────────────────────────────────────
#  PREISE
# ─────────────────────────────────────────────

def coingecko_kurse() -> dict[str, float]:
    ids = ",".join(cid for _, cid in KRYPTO.values())
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ids, "vs_currencies": "usd"}, timeout=15
        )
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
    print("→ CoinGecko (Krypto)...")
    kurse = coingecko_kurse()
    print(f"  {len(kurse)}/{len(KRYPTO)}")
    print("→ yfinance (Aktien)...")
    stocks = yfinance_kurse()
    print(f"  {len(stocks)}/{len(STOCKS)}")
    kurse.update(stocks)
    return kurse

# ─────────────────────────────────────────────
#  STATE
# ─────────────────────────────────────────────

def state_laden() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def state_speichern(kurse: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(kurse, f)

# ─────────────────────────────────────────────
#  NEWS — RSS (Reuters, CoinDesk, CoinTelegraph, Yahoo Finance)
# ─────────────────────────────────────────────

RSS_FEEDS = [
    ("Maerkte",    "https://feeds.reuters.com/reuters/businessNews"),
    ("Maerkte",    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
    ("Krypto",     "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Krypto",     "https://cointelegraph.com/rss"),
    ("Tech",       "https://feeds.reuters.com/reuters/technologyNews"),
    ("Aktien",     "https://finance.yahoo.com/rss/headline?s=AMD"),
    ("Aktien",     "https://finance.yahoo.com/rss/headline?s=HOOD"),
    ("Watchlist",  "https://finance.yahoo.com/rss/headline?s=RKLB"),
    ("Watchlist",  "https://finance.yahoo.com/rss/headline?s=CRWV"),
    ("Watchlist",  "https://finance.yahoo.com/rss/headline?s=NBIS"),
]

RSS_LABEL_EMOJI = {
    "Maerkte":   "🌍 Märkte",
    "Krypto":    "₿ Krypto",
    "Tech":      "💾 Tech",
    "Aktien":    "📈 Aktien",
    "Watchlist": "🚀 Watchlist",
}

def rss_fetch(url: str) -> list[str]:
    try:
        r = requests.get(url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; RSSBot/1.0)"},
            timeout=8)
        if not r.ok:
            return []
        root = ElementTree.fromstring(r.content)
        titles = []
        for item in root.findall(".//item")[:3]:
            t = item.findtext("title", "").strip()
            t = re.sub(r"<[^>]+>", "", t)
            t = t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'")
            if t and len(t) > 15:
                titles.append(t)
        return titles
    except Exception as e:
        print(f"  [RSS] {e}")
        return []

def news_senden(now: datetime) -> None:
    jetzt = now.strftime("%d.%m.%Y  %H:%M Uhr")
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "📰  <b>MARKTNEWS</b>",
        f"🕐  {jetzt}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    seen = set()
    aktueller_label = None
    total = 0

    for label_key, url in RSS_FEEDS:
        items = rss_fetch(url)
        neue  = [t for t in items if t not in seen]
        if not neue:
            continue
        display = RSS_LABEL_EMOJI.get(label_key, label_key)
        if label_key != aktueller_label:
            if aktueller_label is not None:
                lines.append("")
            lines.append(f"<b>{display}</b>")
            aktueller_label = label_key
        for t in neue[:2]:
            seen.add(t)
            lines.append(f"  ▸ {t}")
            total += 1

    if total > 0:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        telegram_senden("\n".join(lines))
        print(f"  {total} News gesendet")
    else:
        print("  Keine News erhalten")

# ─────────────────────────────────────────────
#  FORMATIERUNG
# ─────────────────────────────────────────────

def fmt_usd(v: float) -> str:
    if v >= 10000: return f"${v:>11,.0f}"
    if v >= 100:   return f"${v:>11,.2f}"
    if v >= 1:     return f"${v:>11,.3f}"
    return f"${v:>11,.5f}"

def fmt_eur(v: float, rate: float) -> str:
    e = v * rate
    if e >= 10000: return f"{e:>9,.0f}€"
    if e >= 100:   return f"{e:>9,.2f}€"
    if e >= 1:     return f"{e:>9,.3f}€"
    return f"{e:>9,.5f}€"

def pfeil_diff(sym: str, kurs: float, letzter: dict) -> tuple[str, str]:
    ref = letzter.get(sym)
    if not ref or ref <= 0:
        return "⚪", "   —"
    d = (kurs - ref) / ref * 100
    if   d >= 1.0:  return "🟢", f"▲{d:+.1f}%"
    elif d >= 0.1:  return "🟡", f"▲{d:+.1f}%"
    elif d <= -1.0: return "🔴", f"▼{d:.1f}%"
    elif d <= -0.1: return "🟠", f"▼{d:.1f}%"
    return "⚪", "±0.0%"

def get_name(sym: str) -> str:
    if sym in KRYPTO: return KRYPTO[sym][0]
    return STOCKS.get(sym, sym)

def bericht_erstellen(kurse: dict, rate: float, titel: str, letzter: dict) -> str:
    now   = datetime.now(DE_TZ)
    jetzt = now.strftime("%d.%m.  %H:%M Uhr")
    lines = [
        f"<b>━━━ {titel} ━━━</b>",
        f"🕐 {jetzt}  |  💱 1$ = {rate:.4f}€",
        "",
    ]
    for gruppe, syms in GRUPPEN.items():
        lines.append(f"<b>{gruppe}</b>")
        for sym in syms:
            k    = kurse.get(sym)
            name = get_name(sym)
            if k is None:
                lines.append(f"  ⚠️ <i>{name}</i>")
                continue
            emoji, diff = pfeil_diff(sym, k, letzter)
            u = fmt_usd(k)
            e = fmt_eur(k, rate)
            lines.append(
                f"  {emoji} <b>{name}</b>\n"
                f"     <code>{u}  {e}  {diff}</code>"
            )
        lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines).rstrip()

# ─────────────────────────────────────────────
#  TELEGRAM
# ─────────────────────────────────────────────

def telegram_senden(text: str) -> None:
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
        if not r.ok:
            print(f"  [TG] {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"  [TG] {e}")

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    now    = datetime.now(DE_TZ)
    now_ny = datetime.now(US_TZ)
    print(f"=== {now.strftime('%d.%m.%Y %H:%M')} DE / {now_ny.strftime('%H:%M')} NY ===")

    letzter = state_laden()
    erster  = len(letzter) == 0

    rate  = eur_rate()
    kurse = alle_kurse()
    print(f"Kurse: {len(kurse)}, Rate: {rate}")

    # Alarme
    if not erster:
        for sym, k_neu in kurse.items():
            k_alt = letzter.get(sym)
            if not k_alt or k_alt <= 0:
                continue
            diff = (k_neu - k_alt) / k_alt * 100
            if abs(diff) >= ALARM_SCHWELLE_PCT:
                name     = get_name(sym)
                emoji    = "🚀" if diff > 0 else "🔻"
                richtung = "gestiegen" if diff > 0 else "gefallen"
                telegram_senden(
                    f"{emoji} <b>ALARM — {name}</b>\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"<b>{diff:+.2f}%</b> {richtung}\n"
                    f"💵 {fmt_usd(k_alt).strip()} → <b>{fmt_usd(k_neu).strip()}</b>\n"
                    f"💶 {fmt_eur(k_alt,rate).strip()} → <b>{fmt_eur(k_neu,rate).strip()}</b>\n"
                    f"⏰ {now.strftime('%H:%M Uhr')}"
                )
                print(f"  🚨 {sym} {diff:+.2f}%")

    # Titel bestimmen
    if erster:
        titel = "📊 Startkurse"
    elif now_ny.weekday() < 5 and now_ny.hour == 9 and now_ny.minute < 30:
        titel = "🔔 US-Börse öffnet"
    elif now.hour == 20 and now.minute < 15:
        titel = "📅 Tagesbericht"
    else:
        titel = "📊 15-Min Update"

    telegram_senden(bericht_erstellen(kurse, rate, titel, letzter))

    # News alle 6h
    if now.hour in (8, 14, 20) and now.minute < 15:
        print("→ News...")
        news_senden(now)

    state_speichern(kurse)
    print("=== Done ===")

if __name__ == "__main__":
    main()
