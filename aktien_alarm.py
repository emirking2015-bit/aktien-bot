"""
📈 Aktien-Alarm Bot — Telegram
Schönes Format + News alle 6h
"""

import requests
import schedule
import time
import threading
from datetime import datetime
import pytz

TELEGRAM_TOKEN   = "8237176103:AAEWvhsT_rTCglTQr98beByObnnrVqcLAds"
TELEGRAM_CHAT_ID = "8469935458"

ALARM_SCHWELLE_PCT = 3.0
CHECK_INTERVAL_MIN = 15

DE_TZ = pytz.timezone("Europe/Berlin")
US_TZ = pytz.timezone("America/New_York")

# ─────────────────────────────────────────────
#  TICKER
# ─────────────────────────────────────────────

# (Symbol, Anzeigename, CoinGecko-ID oder None)
KRYPTO = {
    "BTC":  ("Bitcoin",     "bitcoin"),
    "ETH":  ("Ethereum",    "ethereum"),
    "SOL":  ("Solana",      "solana"),
    "HYPE": ("Hyperliquid", "hyperliquid"),
}

HALBLEITER = {
    "AMD":  "AMD",
    "INTC": "Intel",
    "MU":   "Micron",
    "NOW":  "ServiceNow",
    "SNDK": "SanDisk",
    "CRWV": "CoreWeave",
    "CRCL": "Circle",
    "NBIS": "Nebius",
    "CGEH": "CGEH",
}

AKTIEN = {
    "HOOD": "Robinhood",
    "RKLB": "Rocket Lab",
    "BE":   "Bloom Energy",
    "IREN": "Iris Energy",
    "ENR":  "Energizer",
    "WDC":  "Western Digital",
    "CAT":  "Caterpillar",
    "TEAM": "Atlassian",
    "FLY":  "Firefly",    # ← NASDAQ: FLY
}

ROHSTOFFE = {
    "GC=F": "Gold",
    "SI=F": "Silber",
}

ALLE_STOCKS = {**HALBLEITER, **AKTIEN, **ROHSTOFFE}

# News-Ticker für Yahoo Finance (Englisch besser für Ergebnisse)
NEWS_ALLGEMEIN = ["^GSPC", "^IXIC", "^DJI"]
NEWS_TICKER_MAP = {
    "BTC-USD": "₿ Bitcoin",
    "ETH-USD": "Ξ Ethereum",
    "SOL-USD": "◎ Solana",
    "AMD":  "AMD",
    "INTC": "Intel",
    "MU":   "Micron",
    "NVDA": "NVIDIA",
    "CRWV": "CoreWeave",
    "HOOD": "Robinhood",
    "RKLB": "Rocket Lab",
    "CAT":  "Caterpillar",
    "FLY":  "Firefly",
    "GC=F": "Gold",
}

# ─────────────────────────────────────────────
#  INTERNER SPEICHER
# ─────────────────────────────────────────────

letzter_kurs:  dict[str, float] = {}
referenz_kurs: dict[str, float] = {}
offset_id:     list[int] = [0]

# ─────────────────────────────────────────────
#  DATENQUELLEN
# ─────────────────────────────────────────────

YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

def eur_rate() -> float:
    try:
        r = requests.get(
            "https://api.frankfurter.app/latest?from=USD&to=EUR",
            timeout=8
        )
        if r.ok:
            return round(r.json()["rates"]["EUR"], 4)
    except Exception as e:
        print(f"[EUR] {e}")
    return 0.91

def yahoo_kurs(ticker: str) -> float | None:
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        r = requests.get(url, headers=YF_HEADERS,
                         params={"interval": "1m", "range": "1d"}, timeout=10)
        if r.ok:
            meta = r.json()["chart"]["result"][0]["meta"]
            p = meta.get("regularMarketPrice") or meta.get("previousClose")
            return round(float(p), 6) if p else None
    except Exception as e:
        print(f"[YF {ticker}] {e}")
    return None

def coingecko_kurse() -> dict[str, float]:
    try:
        ids = ",".join(cid for _, cid in KRYPTO.values())
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ids, "vs_currencies": "usd"}, timeout=10
        )
        if r.ok:
            data = r.json()
            result = {}
            for sym, (_, cid) in KRYPTO.items():
                p = data.get(cid, {}).get("usd")
                if p:
                    result[sym] = round(float(p), 6)
            return result
    except Exception as e:
        print(f"[CoinGecko] {e}")
    return {}

def alle_kurse() -> dict[str, float]:
    kurse = {}
    kurse.update(coingecko_kurse())
    for ticker in ALLE_STOCKS:
        k = yahoo_kurs(ticker)
        if k:
            kurse[ticker] = k
        time.sleep(0.15)
    return kurse

# ─────────────────────────────────────────────
#  NEWS — Yahoo Finance
# ─────────────────────────────────────────────

def yahoo_news(query: str, count: int = 3) -> list[dict]:
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v1/finance/search",
            headers=YF_HEADERS,
            params={"q": query, "newsCount": count, "enableFuzzyQuery": "false"},
            timeout=8
        )
        if r.ok:
            return r.json().get("news", [])[:count]
    except Exception as e:
        print(f"[News {query}] {e}")
    return []

def news_bericht_erstellen() -> str:
    jetzt = datetime.now(DE_TZ).strftime("%d.%m.%Y  %H:%M Uhr")
    zeilen = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📰  <b>MARKTNEWS</b>",
        f"🕐  {jetzt}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    # Allgemeine Marktnews
    zeilen.append("🌍  <b>MARKTÜBERBLICK</b>")
    seen_titles = set()
    for idx_ticker in NEWS_ALLGEMEIN:
        for item in yahoo_news(idx_ticker, 2):
            title = item.get("title", "").strip()
            if title and title not in seen_titles:
                seen_titles.add(title)
                pub = item.get("publisher", "")
                zeilen.append(f"  ▸ <b>{pub}:</b> {title}")
    zeilen.append("")

    # Ticker-spezifische News
    for ticker, label in NEWS_TICKER_MAP.items():
        nachrichten = yahoo_news(ticker, 2)
        neue = [n for n in nachrichten if n.get("title", "") not in seen_titles]
        if not neue:
            continue
        zeilen.append(f"<b>{label}</b>")
        for item in neue[:2]:
            title = item.get("title", "").strip()
            if title:
                seen_titles.add(title)
                pub = item.get("publisher", "")
                zeilen.append(f"  ▸ <b>{pub}:</b> {title}")
        zeilen.append("")

    return "\n".join(zeilen).rstrip()

# ─────────────────────────────────────────────
#  FORMATIERUNG — Kursbericht
# ─────────────────────────────────────────────

def fmt_usd(v: float) -> str:
    if v >= 10000: return f"${v:>10,.0f}"
    if v >= 100:   return f"${v:>10,.2f}"
    if v >= 1:     return f"${v:>10,.3f}"
    return         f"${v:>10,.4f}"

def fmt_eur(v: float, rate: float) -> str:
    e = v * rate
    if e >= 10000: return f"{e:>9,.0f}€"
    if e >= 100:   return f"{e:>9,.2f}€"
    if e >= 1:     return f"{e:>9,.3f}€"
    return         f"{e:>9,.4f}€"

def fmt_diff(sym: str, kurs: float) -> str:
    ref = referenz_kurs.get(sym)
    if not ref or ref <= 0:
        return "     ±0%"
    d = (kurs - ref) / ref * 100
    if d > 0:   return f" <b>+{d:.2f}%</b>"
    if d < 0:   return f" <b>{d:.2f}%</b>"
    return "     ±0%"

def kreis(sym: str, kurs: float) -> str:
    ref = referenz_kurs.get(sym)
    if not ref or ref <= 0:
        return "⚪"
    d = (kurs - ref) / ref * 100
    if d >= 0.05:  return "🟢"
    if d <= -0.05: return "🔴"
    return "⚪"

def kurs_zeile(sym: str, name: str, kurs: float | None, rate: float) -> str:
    if kurs is None:
        return f"  ⚠️  <i>{name}</i>"
    k = kreis(sym, kurs)
    d = fmt_diff(sym, kurs)
    u = fmt_usd(kurs)
    e = fmt_eur(kurs, rate)
    return f"  {k} <b>{name}</b>\n     <code>{u}  {e}</code>  {d}"

def bericht_erstellen(kurse: dict[str, float], rate: float, titel: str) -> str:
    jetzt = datetime.now(DE_TZ).strftime("%d.%m.%Y  %H:%M Uhr")
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📊  <b>{titel}</b>",
        f"🕐  {jetzt}",
        f"💱  <code>1 USD = {rate:.4f} EUR</code>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "🪙  <b>KRYPTO</b>",
    ]
    for sym, (name, _) in KRYPTO.items():
        lines.append(kurs_zeile(sym, name, kurse.get(sym), rate))

    lines += ["", "💾  <b>HALBLEITER &amp; TECH</b>"]
    for sym, name in HALBLEITER.items():
        lines.append(kurs_zeile(sym, name, kurse.get(sym), rate))

    lines += ["", "📈  <b>AKTIEN</b>"]
    for sym, name in AKTIEN.items():
        lines.append(kurs_zeile(sym, name, kurse.get(sym), rate))

    lines += ["", "🪨  <b>ROHSTOFFE</b>"]
    for sym, name in ROHSTOFFE.items():
        lines.append(kurs_zeile(sym, name, kurse.get(sym), rate))

    lines += ["", "━━━━━━━━━━━━━━━━━━━━━━"]
    return "\n".join(lines)

# ─────────────────────────────────────────────
#  TELEGRAM
# ─────────────────────────────────────────────

def telegram_senden(text: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }, timeout=10)
        if not r.ok:
            print(f"[TG] {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"[TG Fehler] {e}")

# ─────────────────────────────────────────────
#  SCHEDULE-FUNKTIONEN
# ─────────────────────────────────────────────

def check_alarme() -> None:
    print(f"[{datetime.now(DE_TZ).strftime('%H:%M')}] Alarm-Check...")
    rate  = eur_rate()
    kurse = alle_kurse()
    jetzt = datetime.now(DE_TZ).strftime("%H:%M Uhr")

    for sym, k_neu in kurse.items():
        if sym in KRYPTO:
            name = KRYPTO[sym][0]
        else:
            name = ALLE_STOCKS.get(sym, sym)
        if sym not in letzter_kurs:
            letzter_kurs[sym] = k_neu
            continue
        k_alt = letzter_kurs[sym]
        diff = (k_neu - k_alt) / k_alt * 100
        if abs(diff) >= ALARM_SCHWELLE_PCT:
            emoji = "🚀📈" if diff > 0 else "🔻📉"
            richtung = "gestiegen" if diff > 0 else "gefallen"
            telegram_senden(
                f"{emoji}  <b>ALARM — {name}</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"Kurs {richtung}: <b>{diff:+.2f}%</b>\n"
                f"💵  {fmt_usd(k_alt).strip()} → <b>{fmt_usd(k_neu).strip()}</b>\n"
                f"💶  {fmt_eur(k_alt, rate).strip()} → <b>{fmt_eur(k_neu, rate).strip()}</b>\n"
                f"⏰  {jetzt}"
            )
            print(f"  ✅ Alarm: {sym} {diff:+.2f}%")
        letzter_kurs[sym] = k_neu

def kursbericht_senden(titel: str = "Kursbericht") -> None:
    rate  = eur_rate()
    kurse = alle_kurse()
    msg   = bericht_erstellen(kurse, rate, titel)
    telegram_senden(msg)
    referenz_kurs.update(kurse)
    letzter_kurs.update(kurse)

def stunden_bericht() -> None:
    now = datetime.now(DE_TZ)
    if not (8 <= now.hour < 23):
        return
    rate  = eur_rate()
    kurse = alle_kurse()
    if referenz_kurs:
        max_diff = max(
            abs((k - referenz_kurs[s]) / referenz_kurs[s] * 100)
            for s, k in kurse.items() if s in referenz_kurs and referenz_kurs[s] > 0
        ) if kurse else 0
        if max_diff < 0.5:
            print("  ⏭️ Kein Bericht (keine Bewegung)")
            return
    msg = bericht_erstellen(kurse, rate, "Stündlicher Bericht")
    telegram_senden(msg)
    referenz_kurs.update(kurse)

def news_bericht_senden() -> None:
    print(f"[{datetime.now(DE_TZ).strftime('%H:%M')}] News-Bericht...")
    try:
        msg = news_bericht_erstellen()
        telegram_senden(msg)
        print("  ✅ News gesendet")
    except Exception as e:
        print(f"  ❌ News Fehler: {e}")

def boersenstart_alert() -> None:
    if datetime.now(US_TZ).weekday() >= 5:
        return
    kursbericht_senden("🔔 US-Börse öffnet")

def tagesbericht() -> None:
    kursbericht_senden("📅 Tagesbericht")

# ─────────────────────────────────────────────
#  TELEGRAM COMMANDS (POLLING)
# ─────────────────────────────────────────────

def handle_command(text: str) -> None:
    cmd = text.strip().lower().split()[0]
    print(f"  [CMD] {cmd}")

    if cmd in ("/start", "/hilfe"):
        telegram_senden(
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🤖  <b>AKTIEN-ALARM BOT</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📌  <b>Befehle:</b>\n"
            "  🔄  /refresh — Kurse sofort\n"
            "  📰  /news    — Aktuelle News\n"
            "  📊  /report  — Tagesbericht\n"
            "  ❓  /hilfe   — Diese Übersicht\n\n"
            f"⚡  Alarm ab ±{ALARM_SCHWELLE_PCT}%\n"
            "📈  Stündl. Bericht (8–23 Uhr)\n"
            "📰  News alle 6h\n"
            "🔔  US-Börsenstart 15:30 Uhr\n"
            "📅  Tagesbericht 20:00 Uhr"
        )
    elif cmd == "/refresh":
        telegram_senden("🔄  Hole aktuelle Kurse...")
        kursbericht_senden("🔄 Manueller Refresh")
    elif cmd == "/news":
        telegram_senden("📰  Hole aktuelle News...")
        news_bericht_senden()
    elif cmd == "/report":
        tagesbericht()
    else:
        telegram_senden(f"❓ Unbekannt: <code>{text}</code>\nVerfügbar: /refresh /news /report /hilfe")

def polling_loop() -> None:
    print("[Polling] Gestartet")
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"timeout": 30, "offset": offset_id[0]},
                timeout=40
            )
            if r.ok:
                for upd in r.json().get("result", []):
                    offset_id[0] = upd["update_id"] + 1
                    text = upd.get("message", {}).get("text", "")
                    if text.startswith("/"):
                        handle_command(text)
        except Exception as e:
            print(f"[Polling] {e}")
            time.sleep(5)

# ─────────────────────────────────────────────
#  START
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("📈 Aktien-Alarm Bot")
    print(f"   {len(ALLE_STOCKS) + len(KRYPTO)} Ticker  |  ±{ALARM_SCHWELLE_PCT}%  |  {CHECK_INTERVAL_MIN}-Min-Check")
    print("=" * 55)

    threading.Thread(target=polling_loop, daemon=True).start()

    telegram_senden(
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖  <b>AKTIEN-ALARM BOT GESTARTET</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌  {len(ALLE_STOCKS) + len(KRYPTO)} Ticker aktiv\n"
        f"⚡  Alarm ab ±{ALARM_SCHWELLE_PCT}% Bewegung\n"
        "📈  Stündl. Bericht (8–23 Uhr)\n"
        "📰  News alle 6h (8, 14, 20 Uhr)\n"
        "🔔  US-Börsenstart 15:30 Uhr\n"
        "📅  Tagesbericht 20:00 Uhr\n\n"
        "Befehle: /refresh  /news  /report  /hilfe"
    )

    # Startkurse
    kursbericht_senden("📊 Startkurse")

    # Zeitplan
    schedule.every(CHECK_INTERVAL_MIN).minutes.do(check_alarme)
    schedule.every().hour.at(":00").do(stunden_bericht)
    schedule.every().day.at("08:00").do(news_bericht_senden)
    schedule.every().day.at("14:00").do(news_bericht_senden)
    schedule.every().day.at("15:30").do(boersenstart_alert)
    schedule.every().day.at("20:00").do(tagesbericht)
    schedule.every().day.at("20:05").do(news_bericht_senden)

    while True:
        schedule.run_pending()
        time.sleep(30)
