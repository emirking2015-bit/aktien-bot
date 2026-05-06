"""
📈 Aktien-Alarm Bot — Telegram
Preisquellen:
  Aktien       → Twelve Data (kostenlos, 800 req/Tag, läuft auf Cloud)
  Krypto       → Twelve Data (gleicher Key)
  Rohstoffe    → Twelve Data
  EUR/USD      → Twelve Data
"""

import requests
import schedule
import time
import threading
from datetime import datetime
import pytz

# ─────────────────────────────────────────────
#  ⚙️  KONFIGURATION — hier anpassen!
# ─────────────────────────────────────────────

TELEGRAM_TOKEN    = "8237176103:AAEWvhsT_rTCglTQr98beByObnnrVqcLAds"
TELEGRAM_CHAT_ID  = "8469935458"

# ⬇️  Kostenlosen Key holen: https://twelvedata.com (2 Min Registrierung)
TWELVE_DATA_KEY   = "DEIN_API_KEY_HIER"

ALARM_SCHWELLE_PCT  = 3.0
CHECK_INTERVAL_MIN  = 15

DE_TZ = pytz.timezone("Europe/Berlin")
US_TZ = pytz.timezone("America/New_York")

# ─────────────────────────────────────────────
#  TICKER-LISTEN
#  Twelve Data Format:
#    US-Aktien  : "AMD", "INTC" usw.
#    Krypto     : "BTC/USD", "ETH/USD" usw.
#    DE-Aktien  : "ENR:XETRA" (Siemens Energy)
#    KR-Aktien  : "005930:KRX" (Samsung Electronics)
#    Gold/Silber: "XAU/USD", "XAG/USD"
#    EUR/USD    : "EUR/USD"
# ─────────────────────────────────────────────

# (Anzeigename, Twelve-Data-Symbol)
ALLE_TICKER = {
    # ── Krypto ──────────────────────────────
    "BTC":   ("Bitcoin",          "BTC/USD"),
    "ETH":   ("Ethereum",         "ETH/USD"),
    "SOL":   ("Solana",           "SOL/USD"),
    "HYPE":  ("Hyperliquid",      "HYPE/USD"),
    # ── Halbleiter & Tech ───────────────────
    "AMD":   ("AMD",              "AMD"),
    "INTC":  ("Intel",            "INTC"),
    "MU":    ("Micron",           "MU"),
    "NOW":   ("ServiceNow",       "NOW"),
    "SNDK":  ("SanDisk",          "SNDK"),
    "CRWV":  ("CoreWeave",        "CRWV"),
    "CRCL":  ("Circle",           "CRCL"),
    "NBIS":  ("Nebius",           "NBIS"),
    "CGEH":  ("CGEH",             "CGEH"),
    # ── Aktien ──────────────────────────────
    "HOOD":  ("Robinhood",        "HOOD"),
    "RKLB":  ("Rocket Lab",       "RKLB"),
    "BE":    ("Bloom Energy",     "BE"),
    "IREN":  ("Iris Energy",      "IREN"),
    "WDC":   ("Western Digital",  "WDC"),
    "CAT":   ("Caterpillar",      "CAT"),
    "TEAM":  ("Atlassian",        "TEAM"),
    "FLY":   ("Firefly",          "FLY"),
    "ENR":   ("Siemens Energy",   "ENR:XETRA"),
    "SAM":   ("Samsung",          "005930:KRX"),
    # ── Rohstoffe ───────────────────────────
    "GOLD":  ("Gold",             "XAU/USD"),
    "SILB":  ("Silber",           "XAG/USD"),
}

# Gruppen für den Bericht
GRUPPEN = {
    "🪙  KRYPTO":              ["BTC", "ETH", "SOL", "HYPE"],
    "💾  HALBLEITER &amp; TECH": ["AMD", "INTC", "MU", "NOW", "SNDK", "CRWV", "CRCL", "NBIS", "CGEH"],
    "📈  AKTIEN":              ["HOOD", "RKLB", "BE", "IREN", "WDC", "CAT", "TEAM", "FLY", "ENR", "SAM"],
    "🪨  ROHSTOFFE":           ["GOLD", "SILB"],
}

# ─────────────────────────────────────────────
#  SPEICHER
# ─────────────────────────────────────────────

letzter_kurs:  dict[str, float] = {}
referenz_kurs: dict[str, float] = {}
offset_id:     list[int] = [0]

# ─────────────────────────────────────────────
#  TWELVE DATA — Batch-Preisabruf
# ─────────────────────────────────────────────

def twelve_batch() -> dict[str, float]:
    """
    Holt alle Preise in 2 Batch-Anfragen (Aktien + Krypto/Rohstoffe).
    Twelve Data erlaubt mehrere Symbole pro Anfrage mit Komma getrennt.
    Gibt {unsere_id: preis} zurück.
    """
    # Alle Twelve-Data-Symbole mit unserer ID verknüpfen
    td_map = {v[1]: k for k, v in ALLE_TICKER.items()}  # "AMD" → "AMD"
    all_symbols = ",".join(v[1] for v in ALLE_TICKER.values())

    result = {}
    try:
        r = requests.get(
            "https://api.twelvedata.com/price",
            params={"symbol": all_symbols, "apikey": TWELVE_DATA_KEY},
            timeout=20
        )
        if not r.ok:
            print(f"[Twelve Data] HTTP {r.status_code}: {r.text[:200]}")
            return result

        data = r.json()

        # Wenn nur 1 Symbol, kommt dict direkt — bei mehreren ist es verschachtelt
        if "price" in data:
            # Einzel-Rückgabe
            pass
        else:
            for td_sym, val in data.items():
                our_id = td_map.get(td_sym)
                if not our_id:
                    continue
                if isinstance(val, dict) and "price" in val:
                    try:
                        result[our_id] = round(float(val["price"]), 6)
                    except (ValueError, TypeError):
                        pass
                elif isinstance(val, dict) and "code" in val:
                    print(f"  [Twelve Data] {td_sym}: {val.get('message','Fehler')}")

    except Exception as e:
        print(f"[Twelve Data Fehler] {e}")

    return result


def eur_rate_twelve() -> float:
    """EUR/USD über Twelve Data."""
    try:
        r = requests.get(
            "https://api.twelvedata.com/price",
            params={"symbol": "EUR/USD", "apikey": TWELVE_DATA_KEY},
            timeout=8
        )
        if r.ok:
            data = r.json()
            price = data.get("price")
            if price:
                return round(float(price), 4)
    except Exception as e:
        print(f"[EUR/USD] {e}")
    return 0.91


def alle_kurse() -> tuple[dict[str, float], float]:
    """Gibt (kurse_dict, eur_rate) zurück."""
    print("  → Twelve Data (alle Ticker)...")
    kurse = twelve_batch()
    rate  = eur_rate_twelve()
    print(f"     {len(kurse)}/{len(ALLE_TICKER)} Kurse  |  EUR/USD: {rate}")
    return kurse, rate

# ─────────────────────────────────────────────
#  NEWS (Yahoo Finance — nur für News, kein Preis)
# ─────────────────────────────────────────────

NEWS_QUERIES = {
    "^GSPC":   "🌍 Markt",
    "BTC-USD": "₿ Bitcoin",
    "AMD":     "AMD",
    "INTC":    "Intel",
    "CRWV":    "CoreWeave",
    "ENR.DE":  "Siemens Energy",
    "HOOD":    "Robinhood",
    "RKLB":    "Rocket Lab",
    "CAT":     "Caterpillar",
    "FLY":     "Firefly",
}

def yahoo_news(query: str, count: int = 2) -> list[dict]:
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v1/finance/search",
            headers={"User-Agent": "Mozilla/5.0"},
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
    if len(zeilen) <= 5:
        zeilen.append("  <i>Keine News verfügbar</i>")
    return "\n".join(zeilen).rstrip()

# ─────────────────────────────────────────────
#  FORMATIERUNG
# ─────────────────────────────────────────────

def fmt_usd(v: float) -> str:
    if v >= 10000: return f"${v:,.0f}"
    if v >= 100:   return f"${v:,.2f}"
    if v >= 1:     return f"${v:,.3f}"
    return f"${v:.5f}"

def fmt_eur(v: float, rate: float) -> str:
    e = v * rate
    if e >= 10000: return f"{e:,.0f}€"
    if e >= 100:   return f"{e:,.2f}€"
    if e >= 1:     return f"{e:,.3f}€"
    return f"{e:.5f}€"

def get_pfeil_diff(sym: str, kurs: float) -> tuple[str, str]:
    ref = referenz_kurs.get(sym)
    if not ref or ref <= 0:
        return "⚪", ""
    d = (kurs - ref) / ref * 100
    if d >= 0.05:  return "🟢", f"▲ +{d:.2f}%"
    if d <= -0.05: return "🔴", f"▼ {d:.2f}%"
    return "⚪", "±0%"

def kurs_zeile(sym: str, kurs: float | None, rate: float) -> str:
    name = ALLE_TICKER[sym][0]
    if kurs is None:
        return f"  ⚠️  <i>{name}</i>  <code>—</code>"
    emoji, diff = get_pfeil_diff(sym, kurs)
    u = fmt_usd(kurs)
    e = fmt_eur(kurs, rate)
    diff_part = f"  <b>{diff}</b>" if diff else ""
    return f"  {emoji} <b>{name}</b>\n      <code>{u:>13}  {e:>11}</code>{diff_part}"

def bericht_erstellen(kurse: dict[str, float], rate: float, titel: str) -> str:
    jetzt = datetime.now(DE_TZ).strftime("%d.%m.%Y  %H:%M Uhr")
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📊  <b>{titel}</b>",
        f"🕐  {jetzt}",
        f"💱  <code>1 USD = {rate:.4f} EUR</code>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    for gruppe, syms in GRUPPEN.items():
        lines.append(f"<b>{gruppe}</b>")
        for sym in syms:
            lines.append(kurs_zeile(sym, kurse.get(sym), rate))
        lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
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
    kurse, rate = alle_kurse()

    # Alarm bei ±3%
    jetzt_str = datetime.now(DE_TZ).strftime("%H:%M Uhr")
    for sym, k_neu in kurse.items():
        name = ALLE_TICKER[sym][0]
        if sym not in letzter_kurs:
            letzter_kurs[sym] = k_neu
            continue
        k_alt = letzter_kurs[sym]
        if k_alt <= 0:
            continue
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
            print(f"  🚨 {sym} {diff:+.2f}%")

    letzter_kurs.update(kurse)
    telegram_senden(bericht_erstellen(kurse, rate, "15-Min Kursbericht"))
    referenz_kurs.update(kurse)
    print(f"  ✅ Bericht gesendet ({len(kurse)} Kurse)")


def boersenstart_alert() -> None:
    if datetime.now(US_TZ).weekday() >= 5:
        return
    kurse, rate = alle_kurse()
    referenz_kurs.update(kurse)
    letzter_kurs.update(kurse)
    telegram_senden(bericht_erstellen(kurse, rate, "🔔 US-Börse öffnet"))


def tagesbericht() -> None:
    kurse, rate = alle_kurse()
    telegram_senden(bericht_erstellen(kurse, rate, "📅 Tagesbericht"))
    referenz_kurs.update(kurse)
    letzter_kurs.update(kurse)


def news_bericht_senden() -> None:
    print(f"[{datetime.now(DE_TZ).strftime('%H:%M')}] News...")
    telegram_senden(news_bericht_erstellen())

# ─────────────────────────────────────────────
#  COMMANDS
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
            f"📊  Auto-Bericht alle {CHECK_INTERVAL_MIN} Min\n"
            "📰  News: 8:00 / 14:00 / 20:00 Uhr\n"
            "🔔  US-Börsenstart: 15:30 Uhr"
        )
    elif cmd == "/refresh":
        telegram_senden("🔄  Hole Kurse...")
        kurse, rate = alle_kurse()
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
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"timeout": 30, "offset": offset_id[0]}, timeout=40
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
    print("📈 Aktien-Alarm Bot (Twelve Data)")
    print(f"   {len(ALLE_TICKER)} Ticker  |  ±{ALARM_SCHWELLE_PCT}%  |  {CHECK_INTERVAL_MIN}-Min")
    print("=" * 55)

    if TWELVE_DATA_KEY == "DEIN_API_KEY_HIER":
        print("⛔ FEHLER: Bitte erst API-Key von twelvedata.com eintragen!")
        telegram_senden(
            "⛔ <b>Fehler: Kein API-Key!</b>\n\n"
            "Bitte auf <code>twelvedata.com</code> kostenlos registrieren,\n"
            "API-Key holen und in <code>aktien_alarm.py</code> bei\n"
            "<code>TWELVE_DATA_KEY</code> eintragen."
        )
        exit(1)

    threading.Thread(target=polling_loop, daemon=True).start()

    telegram_senden(
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖  <b>BOT GESTARTET</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌  {len(ALLE_TICKER)} Ticker aktiv\n"
        f"⚡  Alarm ab ±{ALARM_SCHWELLE_PCT}%\n"
        f"📊  Bericht alle {CHECK_INTERVAL_MIN} Min\n"
        "📰  News: 8:00 / 14:00 / 20:00 Uhr\n"
        "🔔  US-Börsenstart: 15:30 Uhr\n\n"
        "Befehle: /refresh  /news  /report  /hilfe"
    )

    kurse, rate = alle_kurse()
    referenz_kurs.update(kurse)
    letzter_kurs.update(kurse)
    telegram_senden(bericht_erstellen(kurse, rate, "📊 Startkurse"))

    schedule.every(CHECK_INTERVAL_MIN).minutes.do(routine_15min)
    schedule.every().day.at("08:00").do(news_bericht_senden)
    schedule.every().day.at("14:00").do(news_bericht_senden)
    schedule.every().day.at("15:30").do(boersenstart_alert)
    schedule.every().day.at("20:00").do(tagesbericht)
    schedule.every().day.at("20:05").do(news_bericht_senden)

    while True:
        schedule.run_pending()
        time.sleep(30)
