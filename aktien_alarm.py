"""
📈 Aktien-Alarm Bot — Telegram
Preisquellen:
  Aktien/Rohstoffe → Stooq.com (zuverlässig auf Cloud-Servern, kein API-Key)
  Krypto           → CoinGecko (kostenlos)
  EUR/USD          → frankfurter.app
"""

import requests
import schedule
import time
import threading
import csv
import io
from datetime import datetime
import pytz

TELEGRAM_TOKEN   = "8237176103:AAEWvhsT_rTCglTQr98beByObnnrVqcLAds"
TELEGRAM_CHAT_ID = "8469935458"

ALARM_SCHWELLE_PCT = 3.0
CHECK_INTERVAL_MIN = 15

DE_TZ = pytz.timezone("Europe/Berlin")
US_TZ = pytz.timezone("America/New_York")

# ─────────────────────────────────────────────
#  TICKER  (Display-Name, Stooq-Symbol)
#  US-Aktien: symbol.us | DE: symbol.de | KR: 005930.kr
#  Stooq-Rohstoffe: xauusd, xagusd
# ─────────────────────────────────────────────

KRYPTO = {
    "BTC":  ("Bitcoin",          "bitcoin"),
    "ETH":  ("Ethereum",         "ethereum"),
    "SOL":  ("Solana",           "solana"),
    "HYPE": ("Hyperliquid",      "hyperliquid"),
}

# (Anzeigename, Stooq-Ticker, Währung)
STOCKS = {
    # Halbleiter & Tech
    "AMD":   ("AMD",             "amd.us",    "USD"),
    "INTC":  ("Intel",           "intc.us",   "USD"),
    "MU":    ("Micron",          "mu.us",     "USD"),
    "NOW":   ("ServiceNow",      "now.us",    "USD"),
    "SNDK":  ("SanDisk",         "sndk.us",   "USD"),
    "CRWV":  ("CoreWeave",       "crwv.us",   "USD"),
    "CRCL":  ("Circle",          "crcl.us",   "USD"),
    "NBIS":  ("Nebius",          "nbis.us",   "USD"),
    "CGEH":  ("CGEH",            "cgeh.us",   "USD"),
    # Aktien
    "HOOD":  ("Robinhood",       "hood.us",   "USD"),
    "RKLB":  ("Rocket Lab",      "rklb.us",   "USD"),
    "BE":    ("Bloom Energy",    "be.us",     "USD"),
    "IREN":  ("Iris Energy",     "iren.us",   "USD"),
    "WDC":   ("Western Digital", "wdc.us",    "USD"),
    "CAT":   ("Caterpillar",     "cat.us",    "USD"),
    "TEAM":  ("Atlassian",       "team.us",   "USD"),
    "FLY":   ("Firefly",         "fly.us",    "USD"),
    "SMEGF": ("Siemens Energy",  "smegf.us",  "USD"),  # OTC US
    "SSNLF": ("Samsung",         "ssnlf.us",  "USD"),  # OTC US
    # Rohstoffe
    "GOLD":  ("Gold",            "xauusd",    "USD"),
    "SILB":  ("Silber",          "xagusd",    "USD"),
}

# Interne Kürzel → Anzeigename (für Alarm-Nachrichten)
def get_name(sym: str) -> str:
    if sym in KRYPTO:
        return KRYPTO[sym][0]
    if sym in STOCKS:
        return STOCKS[sym][0]
    return sym

# ─────────────────────────────────────────────
#  SPEICHER
# ─────────────────────────────────────────────

letzter_kurs:  dict[str, float] = {}
referenz_kurs: dict[str, float] = {}
offset_id:     list[int] = [0]

# ─────────────────────────────────────────────
#  DATENQUELLEN
# ─────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
}

# ── EUR/USD ──────────────────────────────────
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

# ── STOOQ Batch ──────────────────────────────
def stooq_batch(stooq_tickers: list[str]) -> dict[str, float]:
    """
    Stooq CSV-API: liefert mehrere Aktien auf einmal.
    Format: https://stooq.com/q/l/?s=amd.us,intc.us&f=sd2t2ohlcv&h&e=csv
    Gibt {stooq_ticker: kurs} zurück.
    """
    result = {}
    # Stooq erlaubt bis zu ~50 Ticker pro Anfrage
    for i in range(0, len(stooq_tickers), 40):
        batch = stooq_tickers[i:i+40]
        symbols = ",".join(batch)
        try:
            url = f"https://stooq.com/q/l/?s={symbols}&f=sd2t2ohlcv&h&e=csv"
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.ok:
                reader = csv.DictReader(io.StringIO(r.text))
                for row in reader:
                    sym = row.get("Symbol", "").lower().strip()
                    close = row.get("Close", "").strip()
                    # Stooq gibt "N/D" wenn kein Kurs
                    if close and close not in ("N/D", "0.00", ""):
                        try:
                            result[sym] = round(float(close), 6)
                        except ValueError:
                            pass
            else:
                print(f"[Stooq] HTTP {r.status_code}")
        except Exception as e:
            print(f"[Stooq Fehler] {e}")
        time.sleep(0.5)
    return result

# ── CoinGecko ─────────────────────────────────
def coingecko_kurse() -> dict[str, float]:
    try:
        ids = ",".join(cid for _, cid in KRYPTO.values())
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ids, "vs_currencies": "usd"},
            timeout=12
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

# ── Alle Kurse holen ──────────────────────────
def alle_kurse() -> dict[str, float]:
    print("  → CoinGecko (Krypto)...")
    kurse = coingecko_kurse()
    print(f"     {len(kurse)}/{len(KRYPTO)} Krypto")

    print("  → Stooq (Aktien & Rohstoffe)...")
    # Stooq-Ticker-Liste aufbauen
    stooq_map = {v[1]: k for k, v in STOCKS.items()}  # stooq_sym → unsere_id
    stooq_list = [v[1] for v in STOCKS.values()]
    stooq_result = stooq_batch(stooq_list)

    # Stooq-Ergebnis auf unsere IDs mappen
    mapped = 0
    for stooq_sym, price in stooq_result.items():
        our_id = stooq_map.get(stooq_sym)
        if our_id:
            kurse[our_id] = price
            mapped += 1

    print(f"     {mapped}/{len(STOCKS)} Aktien")
    return kurse

# ─────────────────────────────────────────────
#  NEWS (Yahoo Finance)
# ─────────────────────────────────────────────

NEWS_QUERIES = {
    "^GSPC":    "🌍 Markt",
    "BTC-USD":  "₿ Bitcoin",
    "ETH-USD":  "Ξ Ethereum",
    "AMD":      "AMD",
    "INTC":     "Intel",
    "CRWV":     "CoreWeave",
    "ENR.DE":   "Siemens Energy",
    "HOOD":     "Robinhood",
    "RKLB":     "Rocket Lab",
    "CAT":      "Caterpillar",
    "FLY":      "Firefly",
}

def yahoo_news(query: str, count: int = 2) -> list[dict]:
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v1/finance/search",
            headers=HEADERS,
            params={"q": query, "newsCount": count},
            timeout=8
        )
        if r.ok:
            return r.json().get("news", [])[:count]
    except Exception:
        pass
    return []

def news_bericht_erstellen() -> str:
    jetzt = datetime.now(DE_TZ).strftime("%d.%m.%Y  %H:%M Uhr")
    zeilen = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "📰  <b>MARKTNEWS</b>",
        f"🕐  {jetzt}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    seen = set()
    for query, label in NEWS_QUERIES.items():
        items = yahoo_news(query, 2)
        neue = [n for n in items if n.get("title", "") not in seen]
        if not neue:
            continue
        zeilen.append(f"<b>{label}</b>")
        for item in neue[:2]:
            t = item.get("title", "").strip()
            if t:
                seen.add(t)
                pub = item.get("publisher", "")
                zeilen.append(f"  ▸ <b>{pub}:</b> {t}")
        zeilen.append("")
    return "\n".join(zeilen).rstrip()

# ─────────────────────────────────────────────
#  FORMATIERUNG
# ─────────────────────────────────────────────

def fmt_usd(v: float) -> str:
    if v >= 10000: return f"${v:,.0f}"
    if v >= 100:   return f"${v:,.2f}"
    if v >= 1:     return f"${v:,.3f}"
    return f"${v:,.4f}"

def fmt_eur(v: float, rate: float) -> str:
    e = v * rate
    if e >= 10000: return f"{e:,.0f}€"
    if e >= 100:   return f"{e:,.2f}€"
    if e >= 1:     return f"{e:,.3f}€"
    return f"{e:,.4f}€"

def get_pfeil_diff(sym: str, kurs: float) -> tuple[str, str]:
    ref = referenz_kurs.get(sym)
    if not ref or ref <= 0:
        return "⚪", ""
    d = (kurs - ref) / ref * 100
    if d >= 0.05:  return "🟢", f"▲ +{d:.2f}%"
    if d <= -0.05: return "🔴", f"▼ {d:.2f}%"
    return "⚪", "±0%"

def kurs_zeile(sym: str, name: str, kurs: float | None, rate: float) -> str:
    if kurs is None:
        return f"  ⚠️  <i>{name}</i>  <code>—</code>"
    emoji, diff = get_pfeil_diff(sym, kurs)
    u = fmt_usd(kurs)
    e = fmt_eur(kurs, rate)
    diff_part = f"  <b>{diff}</b>" if diff else ""
    return (
        f"  {emoji} <b>{name}</b>\n"
        f"      <code>{u:>12}  {e:>10}</code>{diff_part}"
    )

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
    for sym in KRYPTO:
        name = KRYPTO[sym][0]
        lines.append(kurs_zeile(sym, name, kurse.get(sym), rate))

    halbleiter = ["AMD", "INTC", "MU", "NOW", "SNDK", "CRWV", "CRCL", "NBIS", "CGEH"]
    lines += ["", "💾  <b>HALBLEITER &amp; TECH</b>"]
    for sym in halbleiter:
        lines.append(kurs_zeile(sym, STOCKS[sym][0], kurse.get(sym), rate))

    aktien = ["HOOD", "RKLB", "BE", "IREN", "WDC", "CAT", "TEAM", "FLY", "SMEGF", "SSNLF"]
    lines += ["", "📈  <b>AKTIEN</b>"]
    for sym in aktien:
        lines.append(kurs_zeile(sym, STOCKS[sym][0], kurse.get(sym), rate))

    lines += ["", "🪨  <b>ROHSTOFFE</b>"]
    for sym in ["GOLD", "SILB"]:
        lines.append(kurs_zeile(sym, STOCKS[sym][0], kurse.get(sym), rate))

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

def routine_15min() -> None:
    jetzt = datetime.now(DE_TZ).strftime("%H:%M")
    print(f"[{jetzt}] 15-Min Routine...")

    rate  = eur_rate()
    kurse = alle_kurse()

    # ── Alarm bei starker Bewegung ──
    jetzt_str = datetime.now(DE_TZ).strftime("%H:%M Uhr")
    for sym, k_neu in kurse.items():
        name = get_name(sym)
        if sym not in letzter_kurs:
            letzter_kurs[sym] = k_neu
            continue
        k_alt = letzter_kurs[sym]
        diff = (k_neu - k_alt) / k_alt * 100
        if abs(diff) >= ALARM_SCHWELLE_PCT:
            emoji    = "🚀📈" if diff > 0 else "🔻📉"
            richtung = "gestiegen" if diff > 0 else "gefallen"
            telegram_senden(
                f"{emoji}  <b>ALARM — {name}</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"Kurs {richtung}: <b>{diff:+.2f}%</b>\n"
                f"💵  {fmt_usd(k_alt)} → <b>{fmt_usd(k_neu)}</b>\n"
                f"💶  {fmt_eur(k_alt, rate)} → <b>{fmt_eur(k_neu, rate)}</b>\n"
                f"⏰  {jetzt_str}"
            )
            print(f"  🚨 Alarm: {sym} {diff:+.2f}%")

    letzter_kurs.update(kurse)

    # ── Kursbericht immer senden ──
    bericht = bericht_erstellen(kurse, rate, "15-Min Kursbericht")
    telegram_senden(bericht)
    referenz_kurs.update(kurse)
    print(f"  ✅ Bericht gesendet ({len(kurse)}/{len(STOCKS)+len(KRYPTO)} Kurse)")


def boersenstart_alert() -> None:
    if datetime.now(US_TZ).weekday() >= 5:
        return
    rate  = eur_rate()
    kurse = alle_kurse()
    referenz_kurs.update(kurse)
    letzter_kurs.update(kurse)
    telegram_senden(bericht_erstellen(kurse, rate, "🔔 US-Börse öffnet"))


def tagesbericht() -> None:
    rate  = eur_rate()
    kurse = alle_kurse()
    telegram_senden(bericht_erstellen(kurse, rate, "📅 Tagesbericht"))
    referenz_kurs.update(kurse)
    letzter_kurs.update(kurse)


def news_bericht_senden() -> None:
    print(f"[{datetime.now(DE_TZ).strftime('%H:%M')}] News...")
    try:
        telegram_senden(news_bericht_erstellen())
    except Exception as e:
        print(f"  ❌ {e}")

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
            f"📊  Kursbericht alle {CHECK_INTERVAL_MIN} Min\n"
            "📰  News um 8:00, 14:00, 20:00 Uhr\n"
            "🔔  US-Börsenstart 15:30 Uhr\n"
            "📅  Tagesbericht 20:00 Uhr"
        )
    elif cmd == "/refresh":
        telegram_senden("🔄  Hole aktuelle Kurse...")
        rate  = eur_rate()
        kurse = alle_kurse()
        telegram_senden(bericht_erstellen(kurse, rate, "🔄 Manueller Refresh"))
        referenz_kurs.update(kurse)
        letzter_kurs.update(kurse)
    elif cmd == "/news":
        telegram_senden("📰  Hole News...")
        news_bericht_senden()
    elif cmd == "/report":
        tagesbericht()
    else:
        telegram_senden(f"❓ Unbekannt: <code>{text}</code>\n→ /hilfe")


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
    print("📈 Aktien-Alarm Bot (Stooq + CoinGecko)")
    print(f"   {len(STOCKS) + len(KRYPTO)} Ticker  |  ±{ALARM_SCHWELLE_PCT}%  |  {CHECK_INTERVAL_MIN}-Min")
    print("=" * 55)

    threading.Thread(target=polling_loop, daemon=True).start()

    telegram_senden(
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖  <b>BOT GESTARTET</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌  {len(STOCKS)+len(KRYPTO)} Ticker aktiv\n"
        f"⚡  Alarm ab ±{ALARM_SCHWELLE_PCT}%\n"
        f"📊  Kursbericht alle {CHECK_INTERVAL_MIN} Min\n"
        "📰  News: 8:00, 14:00, 20:00 Uhr\n"
        "🔔  US-Börsenstart: 15:30 Uhr\n\n"
        "Befehle: /refresh  /news  /report  /hilfe"
    )

    rate_init  = eur_rate()
    kurse_init = alle_kurse()
    referenz_kurs.update(kurse_init)
    letzter_kurs.update(kurse_init)
    telegram_senden(bericht_erstellen(kurse_init, rate_init, "📊 Startkurse"))

    schedule.every(CHECK_INTERVAL_MIN).minutes.do(routine_15min)
    schedule.every().day.at("08:00").do(news_bericht_senden)
    schedule.every().day.at("14:00").do(news_bericht_senden)
    schedule.every().day.at("15:30").do(boersenstart_alert)
    schedule.every().day.at("20:00").do(tagesbericht)
    schedule.every().day.at("20:05").do(news_bericht_senden)

    while True:
        schedule.run_pending()
        time.sleep(30)
