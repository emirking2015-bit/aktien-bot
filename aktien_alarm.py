"""
📈 Aktien-Alarm Bot — Telegram
================================
Datenquellen:
  - Aktien/Rohstoffe : Yahoo Finance (direkte HTTP-Anfrage, kein yfinance)
  - Krypto           : CoinGecko (kostenlos, kein API-Key)
  - EUR/USD          : frankfurter.app (kostenlos, kein API-Key)

Berichte:
  - 15-Min Check  : nur Alarm wenn ≥ 3% Bewegung
  - Stündlicher Report: nur tagsüber (8–23 Uhr), nur wenn sich was bewegt hat
  - 15:30 Uhr     : US-Börsenstart Bericht
  - 20:00 Uhr     : Tagesbericht
  - /refresh      : Manueller Bericht jederzeit
  - /report       : Tagesbericht manuell
  - /hilfe        : Befehlsliste
"""

import requests
import schedule
import time
import threading
from datetime import datetime
import pytz

# ─────────────────────────────────────────────
#  ⚙️  KONFIGURATION
# ─────────────────────────────────────────────

TELEGRAM_TOKEN    = "8237176103:AAEWvhsT_rTCglTQr98beByObnnrVqcLAds"
TELEGRAM_CHAT_ID  = "8469935458"

ALARM_SCHWELLE_PCT  = 3.0   # Einzelalarm ab ±3%
CHECK_INTERVAL_MIN  = 15    # Preischeck alle 15 Min
BERICHT_STUNDE      = True  # Stündlicher Auto-Bericht (nur tagsüber)

DE_TZ = pytz.timezone("Europe/Berlin")
US_TZ = pytz.timezone("America/New_York")

# ─── Aktien → Yahoo Finance Ticker ───────────
STOCKS = {
    "AMD":    "AMD",
    "INTC":   "Intel",
    "MU":     "Micron",
    "NOW":    "ServiceNow",
    "SNDK":   "SanDisk",
    "CRWV":   "CoreWeave",
    "CRCL":   "Circle",
    "NBIS":   "Nebius",
    "CGEH":   "CGEH",
    "HOOD":   "Robinhood",
    "RKLB":   "Rocket Lab",
    "BE":     "Bloom Energy",
    "IREN":   "Iris Energy",
    "ENR":    "Energizer",
    "WDC":    "Western Digital",
    "CAT":    "Caterpillar",
    "TEAM":   "Atlassian",
    "AFLY":   "Firefly",
    "GC=F":   "Gold",
    "SI=F":   "Silber",
}

# ─── Krypto → CoinGecko ID ───────────────────
CRYPTO = {
    "BTC":   ("Bitcoin",      "bitcoin"),
    "ETH":   ("Ethereum",     "ethereum"),
    "SOL":   ("Solana",       "solana"),
    "HYPE":  ("Hyperliquid",  "hyperliquid"),
}

# ─────────────────────────────────────────────
#  Interner Speicher
# ─────────────────────────────────────────────

letzter_kurs:  dict[str, float] = {}   # für Alarm (15-Min)
referenz_kurs: dict[str, float] = {}   # für Pfeil im Bericht
offset_id:     list[int] = [0]

# ─────────────────────────────────────────────
#  EUR/USD Rate — frankfurter.app
# ─────────────────────────────────────────────

def eur_rate() -> float:
    try:
        r = requests.get(
            "https://api.frankfurter.app/latest?from=USD&to=EUR",
            timeout=8
        )
        if r.ok:
            rate = r.json()["rates"]["EUR"]
            return round(rate, 4)
    except Exception as e:
        print(f"[EUR Rate Fehler] {e}")
    return 0.91

def fmt_eur(usd: float, rate: float) -> str:
    val = usd * rate
    if val >= 1000:
        return f"{val:,.0f}€"
    elif val >= 10:
        return f"{val:,.2f}€"
    else:
        return f"{val:.4f}€"

def fmt_usd(usd: float) -> str:
    if usd >= 1000:
        return f"${usd:,.0f}"
    elif usd >= 1:
        return f"${usd:,.2f}"
    else:
        return f"${usd:.4f}"

# ─────────────────────────────────────────────
#  Aktien-Kurse — Yahoo Finance direkt
# ─────────────────────────────────────────────

YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

def yahoo_kurs(ticker: str) -> float | None:
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        params = {"interval": "1m", "range": "1d"}
        r = requests.get(url, headers=YF_HEADERS, params=params, timeout=10)
        if r.ok:
            meta = r.json()["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice") or meta.get("previousClose")
            return round(float(price), 6) if price else None
    except Exception as e:
        print(f"[Yahoo {ticker}] {e}")
    return None

# ─────────────────────────────────────────────
#  Krypto-Kurse — CoinGecko
# ─────────────────────────────────────────────

def coingecko_kurse() -> dict[str, float]:
    try:
        ids = ",".join(coin_id for _, coin_id in CRYPTO.values())
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ids, "vs_currencies": "usd"},
            timeout=10,
        )
        if r.ok:
            data = r.json()
            result = {}
            for sym, (name, coin_id) in CRYPTO.items():
                price = data.get(coin_id, {}).get("usd")
                if price:
                    result[sym] = round(float(price), 6)
            return result
    except Exception as e:
        print(f"[CoinGecko Fehler] {e}")
    return {}

# ─────────────────────────────────────────────
#  Alle Kurse auf einmal holen
# ─────────────────────────────────────────────

def alle_kurse() -> dict[str, float]:
    print("  → Hole Krypto (CoinGecko)...")
    crypto_kurse = coingecko_kurse()

    print("  → Hole Aktien (Yahoo Finance)...")
    stock_kurse = {}
    for ticker in STOCKS:
        k = yahoo_kurs(ticker)
        if k:
            stock_kurse[ticker] = k
        time.sleep(0.2)   # kurze Pause gegen Rate-Limit

    return {**crypto_kurse, **stock_kurse}

# ─────────────────────────────────────────────
#  Telegram
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
            print(f"[TG Fehler] {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"[TG Netzfehler] {e}")

# ─────────────────────────────────────────────
#  Formatierter Kursbericht
# ─────────────────────────────────────────────

def pfeil(ticker: str, kurs: float) -> str:
    ref = referenz_kurs.get(ticker)
    if not ref or ref <= 0:
        return "⚪"
    diff = (kurs - ref) / ref * 100
    if diff >= 0.1:
        return "🟢"
    elif diff <= -0.1:
        return "🔴"
    return "⚪"

def diff_str(ticker: str, kurs: float) -> str:
    ref = referenz_kurs.get(ticker)
    if not ref or ref <= 0:
        return ""
    d = (kurs - ref) / ref * 100
    return f"{d:+.2f}%" if abs(d) >= 0.01 else "±0%"

def bericht_erstellen(kurse: dict[str, float], rate: float, titel: str) -> str:
    jetzt = datetime.now(DE_TZ).strftime("%d.%m.%Y %H:%M Uhr")
    zeilen = [
        f"<b>{titel}</b>",
        f"🕐 {jetzt}",
        f"💱 1 USD = {rate:.4f} EUR",
        "",
    ]

    def zeile(sym: str, name: str) -> str:
        k = kurse.get(sym)
        if not k:
            return f"  ⚠️ {name}"
        p = pfeil(sym, k)
        d = diff_str(sym, k)
        u = fmt_usd(k).ljust(12)
        e = fmt_eur(k, rate).ljust(10)
        d_part = f"  <i>{d}</i>" if d else ""
        return f"  {p} <b>{name}</b>\n     {u}  {e}{d_part}"

    zeilen.append("🪙 <b>Krypto</b>")
    for sym, (name, _) in CRYPTO.items():
        zeilen.append(zeile(sym, name))

    zeilen.append("")
    zeilen.append("💾 <b>Halbleiter &amp; Tech</b>")
    for sym in ["AMD", "INTC", "MU", "NOW", "SNDK", "CRWV", "CRCL", "NBIS", "CGEH"]:
        zeilen.append(zeile(sym, STOCKS[sym]))

    zeilen.append("")
    zeilen.append("📈 <b>Aktien</b>")
    for sym in ["HOOD", "RKLB", "BE", "IREN", "ENR", "WDC", "CAT", "TEAM", "AFLY"]:
        zeilen.append(zeile(sym, STOCKS[sym]))

    zeilen.append("")
    zeilen.append("🪨 <b>Rohstoffe</b>")
    for sym in ["GC=F", "SI=F"]:
        zeilen.append(zeile(sym, STOCKS[sym]))

    return "\n".join(zeilen)

# ─────────────────────────────────────────────
#  15-Min Check — nur Alarm, kein Auto-Bericht
# ─────────────────────────────────────────────

def check_alarme() -> None:
    jetzt_str = datetime.now(DE_TZ).strftime("%H:%M Uhr")
    print(f"[{jetzt_str}] Alarm-Check...")
    rate  = eur_rate()
    kurse = alle_kurse()

    for sym, kurs_neu in kurse.items():
        name = CRYPTO[sym][0] if sym in CRYPTO else STOCKS.get(sym, sym)
        if sym not in letzter_kurs:
            letzter_kurs[sym] = kurs_neu
            continue
        kurs_alt = letzter_kurs[sym]
        diff = (kurs_neu - kurs_alt) / kurs_alt * 100
        if abs(diff) >= ALARM_SCHWELLE_PCT:
            pfeil_emoji = "🚀📈" if diff > 0 else "🔻📉"
            richtung    = "gestiegen" if diff > 0 else "gefallen"
            telegram_senden(
                f"{pfeil_emoji} <b>ALARM: {name}</b>\n"
                f"Kurs {richtung}: <b>{diff:+.2f}%</b>\n"
                f"💵 {fmt_usd(kurs_alt)} → {fmt_usd(kurs_neu)}\n"
                f"💶 {fmt_eur(kurs_alt, rate)} → {fmt_eur(kurs_neu, rate)}\n"
                f"⏰ {jetzt_str}"
            )
            print(f"  ✅ Alarm: {sym} {diff:+.2f}%")
        letzter_kurs[sym] = kurs_neu

# ─────────────────────────────────────────────
#  Stündlicher Bericht (nur tagsüber, nur bei Bewegung)
# ─────────────────────────────────────────────

def stunden_bericht() -> None:
    now = datetime.now(DE_TZ)
    # Nur zwischen 8 und 23 Uhr senden
    if not (8 <= now.hour < 23):
        return
    rate  = eur_rate()
    kurse = alle_kurse()
    # Prüfen ob mindestens ein Kurs sich um > 0.5% bewegt hat
    bewegung = any(
        abs((k - referenz_kurs[s]) / referenz_kurs[s] * 100) >= 0.5
        for s, k in kurse.items()
        if s in referenz_kurs and referenz_kurs[s] > 0
    )
    if not bewegung and referenz_kurs:
        print(f"  ⏭️ Kein Bericht — keine nennenswerte Bewegung")
        return
    bericht = bericht_erstellen(kurse, rate, "📊 Stündlicher Kursbericht")
    telegram_senden(bericht)
    referenz_kurs.update(kurse)

# ─────────────────────────────────────────────
#  US-Börsenstart (15:30 DE-Zeit, nur Werktage)
# ─────────────────────────────────────────────

def boersenstart_alert() -> None:
    if datetime.now(US_TZ).weekday() >= 5:
        return
    rate  = eur_rate()
    kurse = alle_kurse()
    referenz_kurs.update(kurse)
    bericht = bericht_erstellen(kurse, rate, "🔔 US-Börse öffnet — Eröffnungskurse")
    telegram_senden(bericht)
    print("  🔔 Börsenstart gesendet")

# ─────────────────────────────────────────────
#  Tagesbericht 20:00 Uhr
# ─────────────────────────────────────────────

def tagesbericht() -> None:
    rate  = eur_rate()
    kurse = alle_kurse()
    bericht = bericht_erstellen(kurse, rate, "📅 Tagesbericht")
    telegram_senden(bericht)
    referenz_kurs.update(kurse)

# ─────────────────────────────────────────────
#  Telegram Commands
# ─────────────────────────────────────────────

def handle_command(text: str) -> None:
    cmd = text.strip().lower().split()[0]
    print(f"  [CMD] {cmd}")

    if cmd in ("/start", "/hilfe"):
        telegram_senden(
            "👋 <b>Aktien-Alarm Bot</b>\n\n"
            "📌 <b>Befehle:</b>\n"
            "🔄 /refresh — Aktuelle Kurse sofort\n"
            "📊 /report  — Tagesbericht\n"
            "❓ /hilfe   — Diese Übersicht\n\n"
            f"⚡ Alarm ab ±{ALARM_SCHWELLE_PCT}% Bewegung\n"
            "📈 Stündlicher Bericht (8–23 Uhr, nur bei Bewegung)\n"
            "🔔 US-Börsenstart um 15:30 Uhr\n"
            "📅 Tagesbericht um 20:00 Uhr"
        )

    elif cmd == "/refresh":
        telegram_senden("🔄 Hole aktuelle Kurse...")
        rate  = eur_rate()
        kurse = alle_kurse()
        bericht = bericht_erstellen(kurse, rate, "🔄 Manueller Refresh")
        telegram_senden(bericht)
        referenz_kurs.update(kurse)
        letzter_kurs.update(kurse)

    elif cmd == "/report":
        tagesbericht()

    else:
        telegram_senden(f"❓ Unbekannt: {text}\nVerfügbar: /refresh /report /hilfe")

def polling_loop() -> None:
    print("[Polling] Gestartet")
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            r = requests.get(url, params={"timeout": 30, "offset": offset_id[0]}, timeout=40)
            if r.ok:
                for update in r.json().get("result", []):
                    offset_id[0] = update["update_id"] + 1
                    text = update.get("message", {}).get("text", "")
                    if text.startswith("/"):
                        handle_command(text)
        except Exception as e:
            print(f"[Polling Fehler] {e}")
            time.sleep(5)

# ─────────────────────────────────────────────
#  Start
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("📈 Aktien-Alarm Bot gestartet")
    print(f"   {len(STOCKS) + len(CRYPTO)} Ticker  |  Alarm ab ±{ALARM_SCHWELLE_PCT}%")
    print(f"   Alarm-Check alle {CHECK_INTERVAL_MIN} Min")
    print("=" * 55)

    # Polling-Thread
    threading.Thread(target=polling_loop, daemon=True).start()

    # Startnachricht
    telegram_senden(
        "🤖 <b>Aktien-Alarm Bot gestartet!</b>\n\n"
        f"📌 {len(STOCKS) + len(CRYPTO)} Ticker überwacht\n"
        f"⚡ Alarm ab ±{ALARM_SCHWELLE_PCT}% Bewegung\n"
        "📈 Stündlicher Bericht (8–23 Uhr, nur bei Bewegung)\n"
        "🔔 US-Börsenstart 15:30 Uhr\n"
        "📅 Tagesbericht 20:00 Uhr\n\n"
        "Befehle: /refresh  /report  /hilfe"
    )

    # Erster Kursbericht
    rate_init  = eur_rate()
    kurse_init = alle_kurse()
    referenz_kurs.update(kurse_init)
    letzter_kurs.update(kurse_init)
    bericht = bericht_erstellen(kurse_init, rate_init, "📊 Startkurse")
    telegram_senden(bericht)

    # Zeitplan
    schedule.every(CHECK_INTERVAL_MIN).minutes.do(check_alarme)
    schedule.every().hour.at(":00").do(stunden_bericht)
    schedule.every().day.at("15:30").do(boersenstart_alert)
    schedule.every().day.at("20:00").do(tagesbericht)

    while True:
        schedule.run_pending()
        time.sleep(30)
