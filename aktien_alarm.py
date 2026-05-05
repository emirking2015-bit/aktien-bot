"""
📈 Aktien-Alarm Bot — Telegram
===============================
Features:
  - /refresh  → Aktuelle Kurse sofort abrufen
  - /report   → Tagesbericht manuell anfordern
  - /start    → Begrüßung & Befehlsliste
  - Alle 15 Min: formatierter Kursbericht mit ▲▼
  - Alarm bei ±5% Bewegung
  - US-Börsenstart Benachrichtigung (15:30 Uhr DE-Zeit)
  - Preise in USD + EUR
"""

import yfinance as yf
import requests
import schedule
import time
import threading
from datetime import datetime
import pytz

# ─────────────────────────────────────────────
#  ⚙️  KONFIGURATION
# ─────────────────────────────────────────────

TELEGRAM_TOKEN   = "8237176103:AAEWvhsT_rTCglTQr98beByObnnrVqcLAds"
TELEGRAM_CHAT_ID = "8469935458"

AKTIEN = {
    # Krypto
    "BTC-USD":  "Bitcoin",
    "ETH-USD":  "Ethereum",
    "SOL-USD":  "Solana",
    "HYPE-USD": "Hyperliquid",
    # Halbleiter & Tech
    "AMD":      "AMD",
    "INTC":     "Intel",
    "MU":       "Micron",
    "NOW":      "ServiceNow",
    "SNDK":     "SanDisk",
    "CRWV":     "CoreWeave",
    "CRCL":     "Circle",
    "NBIS":     "Nebius",
    "CGEH":     "CGEH",
    # Aktien
    "HOOD":     "Robinhood",
    "RKLB":     "Rocket Lab",
    "BE":       "Bloom Energy",
    "IREN":     "Iris Energy",
    "ENR":      "Energizer",
    "WDC":      "Western Digital",
    "CAT":      "Caterpillar",
    "TEAM":     "Atlassian",
    "AFLY":     "Firefly",
    # Rohstoffe
    "GC=F":     "Gold",
    "SI=F":     "Silber",
}

SCHWELLE_PROZENT   = 5.0   # Einzel-Alarm ab ±5%
CHECK_INTERVAL_MIN = 15    # Kursbericht alle 15 Min

DE_TZ = pytz.timezone("Europe/Berlin")
US_TZ = pytz.timezone("America/New_York")

# ─────────────────────────────────────────────
#  Interner Speicher
# ─────────────────────────────────────────────

letzter_kurs:     dict[str, float] = {}   # für Alarm-Logik
referenz_kurs:    dict[str, float] = {}   # Kurs beim letzten 15-Min-Bericht
offset_id: list[int] = [0]               # für Telegram Polling

# ─────────────────────────────────────────────
#  EUR-Wechselkurs
# ─────────────────────────────────────────────

def eur_rate() -> float:
    try:
        r = yf.Ticker("EURUSD=X").fast_info.last_price
        return round(r, 4) if r and r > 0 else 0.92
    except Exception:
        return 0.92

def fmt_eur(usd: float, rate: float) -> str:
    return f"{usd * rate:,.2f}€"

def fmt_usd(usd: float) -> str:
    return f"${usd:,.2f}" if usd >= 1 else f"${usd:.4f}"

# ─────────────────────────────────────────────
#  Kurs abrufen
# ─────────────────────────────────────────────

def kurs_abrufen(ticker: str) -> float | None:
    try:
        k = yf.Ticker(ticker).fast_info.last_price
        return round(k, 6) if k and k > 0 else None
    except Exception:
        return None

def alle_kurse() -> dict[str, float]:
    ergebnis = {}
    for ticker in AKTIEN:
        k = kurs_abrufen(ticker)
        if k:
            ergebnis[ticker] = k
    return ergebnis

# ─────────────────────────────────────────────
#  Telegram senden
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
            print(f"[TG Fehler] {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[TG Netzfehler] {e}")

# ─────────────────────────────────────────────
#  Formatierter 15-Min Kursbericht
# ─────────────────────────────────────────────

def bericht_erstellen(kurse: dict[str, float], rate: float, titel: str) -> str:
    jetzt = datetime.now(DE_TZ).strftime("%d.%m.%Y %H:%M Uhr")
    zeilen = [f"📊 <b>{titel}</b>", f"🕐 {jetzt}  |  💱 1$ = {rate:.4f}€", ""]

    # Gruppenüberschriften
    gruppen = {
        "🪙 Krypto":           ["BTC-USD", "ETH-USD", "SOL-USD", "HYPE-USD"],
        "💾 Halbleiter & Tech": ["AMD", "INTC", "MU", "NOW", "SNDK", "CRWV", "CRCL", "NBIS", "CGEH"],
        "📈 Aktien":           ["HOOD", "RKLB", "BE", "IREN", "ENR", "WDC", "CAT", "TEAM", "AFLY"],
        "🪨 Rohstoffe":        ["GC=F", "SI=F"],
    }

    for gruppe, tickers in gruppen.items():
        zeilen.append(f"<b>{gruppe}</b>")
        for ticker in tickers:
            name = AKTIEN.get(ticker, ticker)
            kurs = kurse.get(ticker)
            if kurs is None:
                zeilen.append(f"  ⚠️ {name:<16} —")
                continue

            ref = referenz_kurs.get(ticker)
            if ref and ref > 0:
                diff = ((kurs - ref) / ref) * 100
                if diff > 0:
                    pfeil = "🟢▲"
                    diff_str = f"+{diff:.2f}%"
                elif diff < 0:
                    pfeil = "🔴▼"
                    diff_str = f"{diff:.2f}%"
                else:
                    pfeil = "⚪ "
                    diff_str = "  0.00%"
            else:
                pfeil = "⚪ "
                diff_str = "—"

            usd_str = fmt_usd(kurs).rjust(12)
            eur_str = fmt_eur(kurs, rate).rjust(10)
            zeilen.append(f"  {pfeil} <code>{name:<15} {usd_str}  {eur_str}  {diff_str}</code>")
        zeilen.append("")

    return "\n".join(zeilen).rstrip()

# ─────────────────────────────────────────────
#  15-Min Routine
# ─────────────────────────────────────────────

def check_routine() -> None:
    print(f"[{datetime.now(DE_TZ).strftime('%H:%M')}] Routine-Check...")
    rate  = eur_rate()
    kurse = alle_kurse()

    # Einzelalarm bei ±5%
    for ticker, kurs_neu in kurse.items():
        name = AKTIEN[ticker]
        if ticker not in letzter_kurs:
            letzter_kurs[ticker] = kurs_neu
            continue
        kurs_alt = letzter_kurs[ticker]
        diff = ((kurs_neu - kurs_alt) / kurs_alt) * 100
        if abs(diff) >= SCHWELLE_PROZENT:
            pfeil    = "🚀📈" if diff > 0 else "🔻📉"
            richtung = "gestiegen" if diff > 0 else "gefallen"
            jetzt    = datetime.now(DE_TZ).strftime("%H:%M Uhr")
            telegram_senden(
                f"{pfeil} <b>ALARM: {name} ({ticker})</b>\n"
                f"Kurs {richtung}: <b>{diff:+.2f}%</b>\n"
                f"💵 {fmt_usd(kurs_alt)} → {fmt_usd(kurs_neu)}\n"
                f"💶 {fmt_eur(kurs_alt, rate)} → {fmt_eur(kurs_neu, rate)}\n"
                f"⏰ {jetzt}"
            )
        letzter_kurs[ticker] = kurs_neu

    # Formatierter Kursbericht
    bericht = bericht_erstellen(kurse, rate, "15-Min Kursbericht")
    telegram_senden(bericht)

    # Referenz für nächsten Bericht aktualisieren
    referenz_kurs.update(kurse)
    print("  ✅ Bericht gesendet")

# ─────────────────────────────────────────────
#  US-Börsenstart Alert (9:30 NY = je nach Saison)
# ─────────────────────────────────────────────

def boersenstart_alert() -> None:
    now_ny = datetime.now(US_TZ)
    # Nur an Werktagen
    if now_ny.weekday() >= 5:
        return
    rate  = eur_rate()
    kurse = alle_kurse()
    referenz_kurs.update(kurse)  # Reset für frischen Vergleich
    bericht = bericht_erstellen(kurse, rate, "🔔 US-Börse öffnet — Eröffnungskurse")
    telegram_senden(bericht)
    print("  🔔 Börsenstart-Alert gesendet")

# ─────────────────────────────────────────────
#  Tagesbericht 20:00 Uhr
# ─────────────────────────────────────────────

def tagesbericht() -> None:
    rate  = eur_rate()
    kurse = alle_kurse()
    bericht = bericht_erstellen(kurse, rate, "📅 Tagesbericht")
    telegram_senden(bericht)

# ─────────────────────────────────────────────
#  Telegram Commands (Polling)
# ─────────────────────────────────────────────

def handle_command(text: str) -> None:
    cmd = text.strip().lower().split()[0]
    print(f"  [CMD] {cmd}")

    if cmd in ("/start", "/hilfe"):
        telegram_senden(
            "👋 <b>Aktien-Alarm Bot</b>\n\n"
            "Verfügbare Befehle:\n"
            "🔄 /refresh — Aktuelle Kurse sofort\n"
            "📊 /report  — Tagesbericht\n"
            "❓ /hilfe   — Diese Übersicht\n\n"
            f"⚡ Auto-Alarm bei ±{SCHWELLE_PROZENT}%\n"
            f"🔄 Kursbericht alle {CHECK_INTERVAL_MIN} Min\n"
            "🔔 US-Börsenstart Benachrichtigung"
        )
    elif cmd == "/refresh":
        telegram_senden("🔄 Hole aktuelle Kurse...")
        rate  = eur_rate()
        kurse = alle_kurse()
        bericht = bericht_erstellen(kurse, rate, "🔄 Manueller Refresh")
        telegram_senden(bericht)
        referenz_kurs.update(kurse)
    elif cmd == "/report":
        tagesbericht()
    else:
        telegram_senden(f"❓ Unbekannter Befehl: {text}\nTipp: /hilfe")

def polling_loop() -> None:
    """Lauscht auf Telegram-Nachrichten in einem eigenen Thread."""
    print("[Polling] Gestartet")
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params = {"timeout": 30, "offset": offset_id[0]}
            r = requests.get(url, params=params, timeout=40)
            if r.ok:
                data = r.json()
                for update in data.get("result", []):
                    offset_id[0] = update["update_id"] + 1
                    msg = update.get("message", {})
                    text = msg.get("text", "")
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
    print(f"   {len(AKTIEN)} Ticker  |  ±{SCHWELLE_PROZENT}%  |  {CHECK_INTERVAL_MIN}-Min-Check")
    print("=" * 55)

    # Polling-Thread starten
    t = threading.Thread(target=polling_loop, daemon=True)
    t.start()

    # Erster Check + Startnachricht
    telegram_senden(
        "🤖 <b>Aktien-Alarm Bot gestartet!</b>\n\n"
        f"📌 {len(AKTIEN)} Ticker überwacht\n"
        f"⚡ Alarm ab ±{SCHWELLE_PROZENT}%\n"
        f"🔄 Kursbericht alle {CHECK_INTERVAL_MIN} Minuten\n"
        "🔔 US-Börsenstart Alert um 15:30 Uhr\n"
        "💬 Befehle: /refresh  /report  /hilfe"
    )
    check_routine()

    # Zeitplan
    schedule.every(CHECK_INTERVAL_MIN).minutes.do(check_routine)
    schedule.every().day.at("15:30").do(boersenstart_alert)   # US Open (Winterzeit)
    schedule.every().day.at("15:30").do(boersenstart_alert)   # (Sommerzeit: 14:30 — ggf. anpassen)
    schedule.every().day.at("20:00").do(tagesbericht)

    while True:
        schedule.run_pending()
        time.sleep(30)
