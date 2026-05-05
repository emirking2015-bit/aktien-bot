"""
📈 Aktien-Alarm Bot für Telegram
Läuft auf Railway.app — kein PC nötig!
"""

import yfinance as yf
import requests
import schedule
import time
from datetime import datetime

# ─────────────────────────────────────────────
#  ⚙️  KONFIGURATION
# ─────────────────────────────────────────────

TELEGRAM_TOKEN   = "8237176103:AAEWvhsT_rTCglTQr98beByObnnrVqcLAds"
TELEGRAM_CHAT_ID = "8469935458"

AKTIEN = {
    "BTC-USD": "Bitcoin",
    "AMD":     "AMD",
    "INTC":    "Intel",
    "MU":      "Micron",
    "NOW":     "ServiceNow",
    "SNDK":    "SanDisk",
    "HOOD":    "Robinhood",
    "NBIS":    "Nebius",
    "ENR":     "Energizer",
    "WDC":     "Western Digital",
    "RKLB":    "Rocket Lab",
    "BE":      "Bloom Energy",
    "IREN":    "Iris Energy",
    "CRCL":    "Circle",
    "CRWV":    "CoreWeave",
    "CGEH":    "CGEH",
}

SCHWELLE_PROZENT   = 5.0   # Alarm bei ±5%
CHECK_INTERVAL_MIN = 30    # alle 30 Minuten

# ─────────────────────────────────────────────
#  Interner Speicher
# ─────────────────────────────────────────────

letzter_kurs: dict[str, float] = {}

# ─────────────────────────────────────────────
#  EUR-Wechselkurs
# ─────────────────────────────────────────────

def eur_kurs() -> float:
    """Holt den aktuellen USD→EUR Kurs."""
    try:
        kurs = yf.Ticker("EURUSD=X").fast_info.last_price
        if kurs and kurs > 0:
            return round(kurs, 4)
    except Exception:
        pass
    return 0.92  # Fallback falls API nicht erreichbar

def in_eur(usd: float, rate: float) -> str:
    """Wandelt USD-Betrag in EUR um und formatiert ihn."""
    return f"{usd * rate:,.2f} €"

# ─────────────────────────────────────────────
#  Telegram
# ─────────────────────────────────────────────

def telegram_senden(nachricht: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": nachricht,
        "parse_mode": "HTML",
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if not r.ok:
            print(f"[Telegram-Fehler] {r.status_code}: {r.text}")
    except requests.RequestException as e:
        print(f"[Netzwerk-Fehler] {e}")


def test_telegram() -> None:
    namen = "\n".join(f"  • {name} ({ticker})" for ticker, name in AKTIEN.items())
    telegram_senden(
        "🤖 <b>Aktien-Alarm gestartet!</b>\n\n"
        f"📌 Überwache:\n{namen}\n\n"
        f"⚡ Schwelle: ±{SCHWELLE_PROZENT}%\n"
        f"🔄 Check alle {CHECK_INTERVAL_MIN} Minuten\n"
        f"💶 Preise in USD + EUR"
    )

# ─────────────────────────────────────────────
#  Kurs-Abfrage & Alarm-Logik
# ─────────────────────────────────────────────

def kurs_abrufen(ticker: str) -> float | None:
    try:
        kurs = yf.Ticker(ticker).fast_info.last_price
        if kurs and kurs > 0:
            return round(kurs, 4)
    except Exception as e:
        print(f"[Fehler bei {ticker}] {e}")
    return None


def aenderung_prozent(alt: float, neu: float) -> float:
    return ((neu - alt) / alt) * 100


def kurse_pruefen() -> None:
    jetzt = datetime.now().strftime("%d.%m.%Y %H:%M Uhr")
    print(f"[{jetzt}] Prüfe Kurse...")

    rate = eur_kurs()

    for ticker, name in AKTIEN.items():
        kurs_neu = kurs_abrufen(ticker)
        if kurs_neu is None:
            print(f"  ⚠️  {ticker}: kein Kurs erhalten")
            continue

        if ticker not in letzter_kurs:
            letzter_kurs[ticker] = kurs_neu
            print(f"  📌 {ticker}: ${kurs_neu} / {in_eur(kurs_neu, rate)}")
            continue

        kurs_alt = letzter_kurs[ticker]
        diff = aenderung_prozent(kurs_alt, kurs_neu)
        print(f"  {ticker}: ${kurs_alt} → ${kurs_neu} ({diff:+.2f}%)")

        if abs(diff) >= SCHWELLE_PROZENT:
            pfeil    = "🚀📈" if diff > 0 else "🔻📉"
            richtung = "gestiegen" if diff > 0 else "gefallen"

            nachricht = (
                f"{pfeil} <b>{name} ({ticker})</b>\n"
                f"Kurs {richtung}: <b>{diff:+.2f}%</b>\n\n"
                f"💵 USD: <code>${kurs_alt:,.2f}</code> → <code>${kurs_neu:,.2f}</code>\n"
                f"💶 EUR: <code>{in_eur(kurs_alt, rate)}</code> → <code>{in_eur(kurs_neu, rate)}</code>\n\n"
                f"⏰ {jetzt}"
            )
            telegram_senden(nachricht)
            print(f"  ✅ Alarm gesendet für {ticker}!")
            letzter_kurs[ticker] = kurs_neu
        else:
            letzter_kurs[ticker] = kurs_neu

# ─────────────────────────────────────────────
#  Tagesbericht täglich um 20:00 Uhr
# ─────────────────────────────────────────────

def tagesbericht() -> None:
    rate = eur_kurs()
    zeilen = [f"📊 <b>Tagesbericht</b>\n💱 1 USD = {rate:.4f} EUR\n"]

    for ticker, name in AKTIEN.items():
        kurs = kurs_abrufen(ticker)
        if kurs:
            zeilen.append(
                f"• <b>{name}</b> ({ticker})\n"
                f"  💵 <code>${kurs:,.2f}</code>  💶 <code>{in_eur(kurs, rate)}</code>"
            )
        else:
            zeilen.append(f"• {name} ({ticker}): ⚠️ kein Kurs")

    telegram_senden("\n".join(zeilen))

# ─────────────────────────────────────────────
#  Start
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("📈 Aktien-Alarm Bot gestartet")
    print(f"   {len(AKTIEN)} Ticker überwacht")
    print(f"   Schwelle: ±{SCHWELLE_PROZENT}%")
    print(f"   Intervall: {CHECK_INTERVAL_MIN} Minuten")
    print("=" * 50)

    test_telegram()
    kurse_pruefen()

    schedule.every(CHECK_INTERVAL_MIN).minutes.do(kurse_pruefen)
    schedule.every().day.at("20:00").do(tagesbericht)

    while True:
        schedule.run_pending()
        time.sleep(60)
