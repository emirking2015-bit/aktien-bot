"""
📈 Aktien-Alarm Bot — läuft via GitHub Actions alle 15 Min.
Preise: yfinance (Aktien/Rohstoffe) + CoinGecko (Krypto)
State:  GitHub Actions Cache (speichert letzte Kurse zwischen Runs)
"""

import os, json, requests, time
from datetime import datetime
import pytz
import yfinance as yf

# ─────────────────────────────────────────────
#  KONFIGURATION (aus GitHub Secrets)
# ─────────────────────────────────────────────

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

ALARM_SCHWELLE_PCT = 3.0
STATE_FILE         = "/tmp/kurse_state.json"   # GitHub Cache Datei
DE_TZ              = pytz.timezone("Europe/Berlin")
US_TZ              = pytz.timezone("America/New_York")

# ─────────────────────────────────────────────
#  TICKER
# ─────────────────────────────────────────────

KRYPTO = {
    "BTC":  ("Bitcoin",         "bitcoin"),
    "ETH":  ("Ethereum",        "ethereum"),
    "SOL":  ("Solana",          "solana"),
    "HYPE": ("Hyperliquid",     "hyperliquid"),
}

# Yahoo Finance Ticker → Anzeigename
STOCKS = {
    # Halbleiter & Tech
    "AMD":    "AMD",
    "INTC":   "Intel",
    "MU":     "Micron",
    "NOW":    "ServiceNow",
    "SNDK":   "SanDisk",
    "CRWV":   "CoreWeave",
    "CRCL":   "Circle",
    "NBIS":   "Nebius",
    "CGEH":   "CGEH",
    # Aktien
    "HOOD":   "Robinhood",
    "RKLB":   "Rocket Lab",
    "BE":     "Bloom Energy",
    "IREN":   "Iris Energy",
    "WDC":    "Western Digital",
    "CAT":    "Caterpillar",
    "TEAM":   "Atlassian",
    "FLY":    "Firefly",
    "SMEGF":  "Siemens Energy",  # OTC US
    "SSNLF":  "Samsung",         # OTC US
    # Rohstoffe
    "GC=F":  "Gold",
    "SI=F":  "Silber",
}

GRUPPEN = {
    "🪙  KRYPTO":               ["BTC",  "ETH",  "SOL",  "HYPE"],
    "💾  HALBLEITER &amp; TECH": ["AMD",  "INTC", "MU",   "NOW",  "SNDK", "CRWV", "CRCL", "NBIS", "CGEH"],
    "📈  AKTIEN":               ["HOOD", "RKLB", "BE",   "IREN", "WDC",  "CAT",  "TEAM", "FLY",  "SMEGF", "SSNLF"],
    "🪨  ROHSTOFFE":            ["GC=F", "SI=F"],
}

# ─────────────────────────────────────────────
#  PREISE HOLEN
# ─────────────────────────────────────────────

def coingecko_kurse() -> dict[str, float]:
    ids = ",".join(cid for _, cid in KRYPTO.values())
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ids, "vs_currencies": "usd"},
            timeout=15
        )
        if r.ok:
            data = r.json()
            return {
                sym: round(float(data[cid]["usd"]), 6)
                for sym, (_, cid) in KRYPTO.items()
                if cid in data and "usd" in data[cid]
            }
    except Exception as e:
        print(f"[CoinGecko] {e}")
    return {}

def yfinance_kurse() -> dict[str, float]:
    tickers = list(STOCKS.keys())
    result = {}
    try:
        # Batch-Download mit yfinance
        data = yf.download(
            tickers,
            period="1d",
            interval="1m",
            progress=False,
            threads=True,
            auto_adjust=True,
        )
        # Letzten Close-Preis pro Ticker holen
        if "Close" in data.columns.names or isinstance(data.columns, object):
            closes = data["Close"] if "Close" in data else data
            for ticker in tickers:
                try:
                    col = closes[ticker] if ticker in closes else None
                    if col is not None:
                        last = col.dropna().iloc[-1]
                        if last and last > 0:
                            result[ticker] = round(float(last), 6)
                except Exception:
                    pass
    except Exception as e:
        print(f"[yfinance batch] {e}")

    # Fehlende Ticker einzeln nachholen
    missing = [t for t in tickers if t not in result]
    if missing:
        print(f"  Einzelabruf für: {missing}")
        for ticker in missing:
            try:
                info = yf.Ticker(ticker).fast_info
                p = info.last_price
                if p and p > 0:
                    result[ticker] = round(float(p), 6)
                time.sleep(0.2)
            except Exception as e:
                print(f"  [{ticker}] {e}")

    return result

def eur_rate() -> float:
    try:
        # EUR/USD über yfinance
        p = yf.Ticker("EURUSD=X").fast_info.last_price
        if p and p > 0:
            return round(float(p), 4)
    except Exception:
        pass
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=USD&to=EUR", timeout=8)
        if r.ok:
            return round(r.json()["rates"]["EUR"], 4)
    except Exception:
        pass
    return 0.91

def alle_kurse() -> dict[str, float]:
    print("→ CoinGecko (Krypto)...")
    kurse = coingecko_kurse()
    print(f"  {len(kurse)}/{len(KRYPTO)} Krypto")

    print("→ yfinance (Aktien)...")
    stocks = yfinance_kurse()
    print(f"  {len(stocks)}/{len(STOCKS)} Aktien")

    kurse.update(stocks)
    return kurse

# ─────────────────────────────────────────────
#  STATE (letzte Kurse zwischen Runs speichern)
# ─────────────────────────────────────────────

def state_laden() -> dict:
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def state_speichern(kurse: dict) -> None:
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(kurse, f)
    except Exception as e:
        print(f"[State] {e}")

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

def get_pfeil_diff(sym: str, kurs: float, letzter: dict) -> tuple[str, str]:
    ref = letzter.get(sym)
    if not ref or ref <= 0:
        return "⚪", ""
    d = (kurs - ref) / ref * 100
    if d >= 0.05:  return "🟢", f"▲ +{d:.2f}%"
    if d <= -0.05: return "🔴", f"▼ {d:.2f}%"
    return "⚪", "±0%"

def get_name(sym: str) -> str:
    if sym in KRYPTO:  return KRYPTO[sym][0]
    return STOCKS.get(sym, sym)

def kurs_zeile(sym: str, kurs: float | None, rate: float, letzter: dict) -> str:
    name = get_name(sym)
    if kurs is None:
        return f"  ⚠️  <i>{name}</i>"
    emoji, diff = get_pfeil_diff(sym, kurs, letzter)
    u = fmt_usd(kurs)
    e = fmt_eur(kurs, rate)
    diff_part = f"  <b>{diff}</b>" if diff else ""
    return f"  {emoji} <b>{name}</b>\n      <code>{u:>13}  {e:>11}</code>{diff_part}"

def bericht_erstellen(kurse: dict, rate: float, titel: str, letzter: dict) -> str:
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
            lines.append(kurs_zeile(sym, kurse.get(sym), rate, letzter))
        lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

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
            print(f"[TG] {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"[TG] {e}")

# ─────────────────────────────────────────────
#  LOGIK
# ─────────────────────────────────────────────

def main():
    now = datetime.now(DE_TZ)
    now_ny = datetime.now(US_TZ)
    print(f"Bot startet: {now.strftime('%d.%m.%Y %H:%M')} DE / {now_ny.strftime('%H:%M')} NY")

    # Letzte Kurse laden
    letzter = state_laden()
    erster_run = len(letzter) == 0

    # Aktuelle Kurse holen
    rate  = eur_rate()
    kurse = alle_kurse()

    print(f"EUR Rate: {rate}  |  {len(kurse)} Kurse erhalten")

    # ── Alarme prüfen ────────────────────────
    if not erster_run:
        for sym, k_neu in kurse.items():
            k_alt = letzter.get(sym)
            if not k_alt or k_alt <= 0:
                continue
            diff = (k_neu - k_alt) / k_alt * 100
            if abs(diff) >= ALARM_SCHWELLE_PCT:
                name     = get_name(sym)
                emoji    = "🚀📈" if diff > 0 else "🔻📉"
                richtung = "gestiegen" if diff > 0 else "gefallen"
                telegram_senden(
                    f"{emoji}  <b>ALARM — {name}</b>\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"Kurs {richtung}: <b>{diff:+.2f}%</b>\n"
                    f"💵  {fmt_usd(k_alt)} → <b>{fmt_usd(k_neu)}</b>\n"
                    f"💶  {fmt_eur(k_alt, rate)} → <b>{fmt_eur(k_neu, rate)}</b>\n"
                    f"⏰  {now.strftime('%H:%M Uhr')}"
                )
                print(f"  🚨 Alarm: {sym} {diff:+.2f}%")

    # ── 15-Min Kursbericht senden ────────────
    titel = "📊 Startkurse" if erster_run else "15-Min Kursbericht"

    # Sondertitel für US-Börsenstart (9:30 NY)
    if now_ny.hour == 9 and now_ny.minute < 30 and now_ny.weekday() < 5:
        titel = "🔔 US-Börse öffnet"
    # Tagesbericht um 20:00 DE
    elif now.hour == 20 and now.minute < 15:
        titel = "📅 Tagesbericht"

    bericht = bericht_erstellen(kurse, rate, titel, letzter)
    telegram_senden(bericht)

    # ── News alle 6h (8, 14, 20 Uhr) ────────
    if now.hour in (8, 14, 20) and now.minute < 15:
        news_senden()

    # ── State speichern ──────────────────────
    state_speichern(kurse)
    print("✅ Fertig")

def news_senden():
    jetzt = datetime.now(DE_TZ).strftime("%d.%m.%Y  %H:%M Uhr")
    zeilen = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "📰  <b>MARKTNEWS</b>",
        f"🕐  {jetzt}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    queries = {
        "^GSPC":   "🌍 Markt",
        "BTC-USD": "₿ Bitcoin",
        "AMD":     "AMD",
        "INTC":    "Intel",
        "CRWV":    "CoreWeave",
        "HOOD":    "Robinhood",
        "RKLB":    "Rocket Lab",
        "CAT":     "Caterpillar",
        "FLY":     "Firefly",
    }
    seen = set()
    for query, label in queries.items():
        try:
            r = requests.get(
                "https://query1.finance.yahoo.com/v1/finance/search",
                headers={"User-Agent": "Mozilla/5.0"},
                params={"q": query, "newsCount": 2},
                timeout=8
            )
            if not r.ok:
                continue
            items = r.json().get("news", [])
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
        except Exception:
            pass

    if len(zeilen) > 5:
        telegram_senden("\n".join(zeilen).rstrip())

if __name__ == "__main__":
    main()
