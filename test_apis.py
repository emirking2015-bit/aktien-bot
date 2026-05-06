"""
API-Test Script — auf Railway ausführen!
Testet welche Preisquellen auf diesem Server funktionieren.

Ausführen:
    python test_apis.py
"""

import requests

TWELVE_KEY = "DEIN_KEY"   # optional testen
FINNHUB_KEY = "DEIN_KEY"  # optional testen

print("=" * 50)
print("API CONNECTIVITY TEST")
print("=" * 50)

# ── 1. Yahoo Finance ────────────────────────
print("\n[1] Yahoo Finance...")
try:
    r = requests.get(
        "https://query1.finance.yahoo.com/v8/finance/chart/AMD",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=8
    )
    if r.ok:
        price = r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        print(f"    ✅ AMD: ${price}")
    else:
        print(f"    ❌ HTTP {r.status_code}: {r.text[:80]}")
except Exception as e:
    print(f"    ❌ Fehler: {e}")

# ── 2. Stooq ────────────────────────────────
print("\n[2] Stooq.com...")
try:
    r = requests.get(
        "https://stooq.com/q/l/?s=amd.us&f=sd2t2ohlcv&h&e=csv",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=8
    )
    if r.ok and "N/D" not in r.text and len(r.text) > 30:
        print(f"    ✅ Antwort: {r.text.strip()[:120]}")
    else:
        print(f"    ❌ HTTP {r.status_code}: {r.text[:80]}")
except Exception as e:
    print(f"    ❌ Fehler: {e}")

# ── 3. CoinGecko ────────────────────────────
print("\n[3] CoinGecko...")
try:
    r = requests.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids": "bitcoin,ethereum", "vs_currencies": "usd"},
        timeout=8
    )
    if r.ok:
        data = r.json()
        print(f"    ✅ BTC: ${data['bitcoin']['usd']}  ETH: ${data['ethereum']['usd']}")
    else:
        print(f"    ❌ HTTP {r.status_code}: {r.text[:80]}")
except Exception as e:
    print(f"    ❌ Fehler: {e}")

# ── 4. Twelve Data (nur wenn Key eingetragen) ──
if TWELVE_KEY != "DEIN_KEY":
    print("\n[4] Twelve Data...")
    try:
        r = requests.get(
            "https://api.twelvedata.com/price",
            params={"symbol": "AMD,INTC,BTC/USD", "apikey": TWELVE_KEY},
            timeout=10
        )
        if r.ok:
            print(f"    ✅ Antwort: {r.text[:200]}")
        else:
            print(f"    ❌ HTTP {r.status_code}: {r.text[:80]}")
    except Exception as e:
        print(f"    ❌ Fehler: {e}")
else:
    print("\n[4] Twelve Data → übersprungen (kein Key)")

# ── 5. Finnhub (nur wenn Key eingetragen) ──────
if FINNHUB_KEY != "DEIN_KEY":
    print("\n[5] Finnhub...")
    try:
        r = requests.get(
            f"https://finnhub.io/api/v1/quote?symbol=AMD&token={FINNHUB_KEY}",
            timeout=8
        )
        if r.ok:
            data = r.json()
            print(f"    ✅ AMD: ${data.get('c')} (current price)")
        else:
            print(f"    ❌ HTTP {r.status_code}: {r.text[:80]}")
    except Exception as e:
        print(f"    ❌ Fehler: {e}")
else:
    print("\n[5] Finnhub → übersprungen (kein Key)")

# ── 6. EUR/USD ──────────────────────────────
print("\n[6] Frankfurter EUR/USD...")
try:
    r = requests.get("https://api.frankfurter.app/latest?from=USD&to=EUR", timeout=8)
    if r.ok:
        rate = r.json()["rates"]["EUR"]
        print(f"    ✅ 1 USD = {rate} EUR")
    else:
        print(f"    ❌ HTTP {r.status_code}")
except Exception as e:
    print(f"    ❌ Fehler: {e}")

print("\n" + "=" * 50)
print("TEST FERTIG — schick mir den Output!")
print("=" * 50)
