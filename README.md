# 📈 Aktien-Alarm Bot

Läuft via **GitHub Actions** — kostenlos, keine Server, zuverlässig.

## Setup (5 Minuten)

### 1. GitHub Repository erstellen
- github.com → New Repository → Name: `aktien-bot` → Public → Create
- Alle Dateien aus diesem ZIP hochladen

### 2. Secrets eintragen
In deinem Repo: **Settings → Secrets and variables → Actions → New repository secret**

| Name | Wert |
|------|------|
| `TELEGRAM_TOKEN` | `8237176103:AAEWvhsT_rTCglTQr98beByObnnrVqcLAds` |
| `TELEGRAM_CHAT_ID` | `8469935458` |

### 3. Actions aktivieren
- Reiter **Actions** → "I understand my workflows, go ahead and enable them"
- Fertig! Der Bot läuft jetzt automatisch alle 15 Minuten.

### 4. Manuell testen
Actions → "Aktien Alarm Bot" → "Run workflow" → Run workflow

## Features
- 📊 Kursbericht alle 15 Min
- 🚨 Alarm bei ±3% Bewegung
- 📰 News um 8:00, 14:00, 20:00 Uhr
- 🔔 US-Börsenstart Alert
- 💱 Preise in USD + EUR
