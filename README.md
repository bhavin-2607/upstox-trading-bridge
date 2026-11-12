# Upstox Live Market Data Bridge (Excel & Google Sheets)

A universal, high-performance Python trading bridge that streams real-time market data (OHLC, LTP, Volume, Day Changes) from **Upstox API v2** via WebSockets (binary Protobuf decoding) and synchronizes the live data simultaneously to:

1. **Local Microsoft Excel Workbook** on your machine (real-time updating via `xlwings`).
2. **Google Sheets** with **Zero Google Cloud Account setup** (using a lightweight Google Apps Script Webhook).
3. **Universal Local Live Feed Server** (`http://127.0.0.1:8080/live.csv`) for any spreadsheet on macOS, Windows, or Linux.

---

## Features

- **Real-Time Streaming**: Uses Upstox WebSocket V3 with binary Protocol Buffers (`full` feed mode) for sub-second updates of LTP, Open, High, Low, Close, Volume, and point/percentage change.
- **Zero Google Cloud Account Needed**: Feed live OHLC & LTP directly into Google Sheets using a 1-minute Google Apps Script Webhook—no service account JSONs, no GCP console, no OAuth consent screens.
- **Universal & OS-Agnostic**: 100% pure Python with cross-platform path handling (`pathlib.Path`). Runs identically on **macOS**, **Windows**, and **Linux**.
- **Dynamic Watchlist**: Add tickers directly to `config/watchlist.yaml` or type new stock names inside the Excel `Watchlist` tab while the bridge is running—it automatically detects them and subscribes.
- **Simulation Mode**: Test and verify your Excel and Google Sheets dashboards on weekends or after market hours without needing an active live market session.
- **Built-in Local REST & CSV Server**: Exposes `http://127.0.0.1:8080/live.csv` and `/live.json` allowing any spreadsheet (Excel, LibreOffice Calc, Google Sheets) to consume quotes via `=WEBSERVICE()` or Web Queries.

---

## Directory Structure

```
upstox-trading-bridge/
├── install.bat                   # 🚀 1-Click Windows Installer (venv + dependencies + template)
├── run.bat                       # 🚀 1-Click Windows Live Bridge Runner
├── simulate.bat                  # 🚀 1-Click Windows Market Simulation Runner
├── install.sh                    # 1-Click macOS / Linux Installer
├── run.sh                        # 1-Click macOS / Linux Runner
├── watchlist.txt                 # 📝 Watchlist (1 symbol per line, hot-reloading)
├── .env                          # Upstox API keys & Google Sheet Webhook URL
├── .env.example                  # Environment template
├── config/
│   ├── config.yaml               # Settings (refresh rates, sheet names, ports)
│   └── watchlist.yaml            # Default watchlist configuration
├── data/
│   └── Upstox_Live_Market.xlsx   # Live updated workbook
├── templates/
│   └── Upstox_Live_Market.xlsx   # Pre-styled Excel template
├── scripts/
│   └── google_apps_script.js     # Ready-to-paste Google Apps Script code
├── upstox_bridge/
│   ├── core/                     # Config and thread-safe market store
│   ├── auth/                     # OAuth flow and token cache
│   ├── instruments/              # Instrument master download & symbol resolver
│   ├── feed/                     # WebSocket streamer & Protobuf parser
│   └── destinations/             # Excel, Google Sheets Webhook, & Local Server
├── tests/                        # Automated unit tests
├── main.py                       # CLI entrypoint
└── README.md
```

---

## Quick Start Guide

### 🪟 Windows (1-Click Setup)

1. **Install Dependencies & Set Up Environment**:
   - Double-click **`install.bat`** (or open Command Prompt in the folder and run `install.bat`).
   - This automatically checks Python, creates `.venv`, installs all packages from `requirements.txt`, creates `.env`, and generates the pre-styled Excel template!

2. **Configure Credentials**:
   - Open **`.env`** in Notepad.
   - Paste your `UPSTOX_ACCESS_TOKEN` (from [Upstox Developer Console](https://developer.upstox.com)).
   - *(Optional)* Paste your `GOOGLE_SHEET_WEBHOOK_URL` if streaming to Google Sheets.

3. **Start the Bridge**:
   - Double-click **`run.bat`** to start streaming live market data!
   - *(Optional)* Double-click **`simulate.bat`** to test anytime outside market hours.

---

### 🍎 macOS / 🐧 Linux Setup

1. **Run Installer**:
   ```bash
   ./install.sh
   ```
2. **Configure Credentials**:
   ```bash
   nano .env   # Paste your UPSTOX_ACCESS_TOKEN
   ```
3. **Start Bridge**:
   ```bash
   ./run.sh
   ```
   Or run directly with Python:
   ```bash
   source .venv/bin/activate
   python main.py run
   ```

---

## Managing Your Watchlist (`watchlist.txt`)

Managing your watchlist is now **100% automated with zero manual steps**:

Open [`watchlist.txt`](file:///Users/bhavinamesara/Projects/upstox-trading-bridge/watchlist.txt) in the project root and add or remove symbols (one per line):

```text
# Add your trading symbols below:
NIFTY 50
NIFTY BANK
RELIANCE
TCS
HDFCBANK
INFY
```

### Key Automated Features:
- **Zero manual copying or template regeneration**: The bridge automatically sets up Excel and Google Sheets matching `watchlist.txt`.
- **Live Auto-Reload**: You can edit and save `watchlist.txt` **anytime while the tool is running**—it detects changes immediately and updates both local Excel and Google Sheets on the fly!

You **do not** need any Google Cloud Console account or service account key.

1. Open your target **Google Sheet** in your browser.
2. In the top menu, click **Extensions** → **Apps Script**.
3. Delete any default code in the editor, and copy-paste the entire contents of [scripts/google_apps_script.js](file:///Users/bhavinamesara/Projects/upstox-trading-bridge/scripts/google_apps_script.js).
4. Click **Deploy** (top right blue button) → **New deployment**.
5. Click the gear icon next to *Select type* → choose **Web app**.
6. Set:
   - **Description**: `Upstox Live Feed`
   - **Execute as**: `Me (your_email@gmail.com)`
   - **Who has access**: `Anyone` *(required so your local Python script can post updates)*
7. Click **Deploy**, authorize access with your Google account.
8. Copy the generated **Web app URL** (starts with `https://script.google.com/macros/s/...`).
9. Paste it into your `.env` file as `GOOGLE_SHEET_WEBHOOK_URL`.

#### Verify Google Sheets Connection:
Test your webhook immediately:

```bash
python main.py test-gsheet
```

You should see a success message, and a `LiveMarket` tab will appear in your Google Sheet populated with a test row!

---

## Authenticating with Upstox

To generate today's Upstox access token:

```bash
python main.py login
```

This opens your browser to the Upstox login dialog. Once you log in, the tool captures the redirect authorization code and saves a cached access token into `.token_cache.json`. You only need to run this once per trading day.

---

## Running the Live Bridge

To start streaming live market data to both Excel and Google Sheets:

```bash
python main.py run
```

### Command Options:
- **Custom symbols**:
  ```bash
  python main.py run --symbols "NIFTY 50,BANKNIFTY,RELIANCE,INFY,TCS"
  ```
- **Excel only** (disable Google Sheets):
  ```bash
  python main.py run --no-gsheet
  ```
- **Google Sheets only** (disable Excel):
  ```bash
  python main.py run --no-excel
  ```

---

## Simulation Mode (Test After Market Hours)

To test your Excel spreadsheet and Google Sheets dashboard on weekends or after market hours:

```bash
python main.py simulate
```

This streams realistic synthetic ticks (LTP, OHLC, and Volume) in real time so you can inspect formulas, colors, and live updates without waiting for market hours.

---

## Other Useful CLI Commands

- **Search Upstox Symbol Keys**:
  ```bash
  python main.py search RELIANCE
  python main.py search NIFTY
  ```
- **Test Local Excel Output**:
  ```bash
  python main.py test-excel
  ```
- **Regenerate Clean Excel Template**:
  ```bash
  python main.py create-template
  ```
- **Run Unit Tests**:
  ```bash
  python -m unittest discover tests
  ```

---

## Live Data Schema

| Column | Header | Description |
|---|---|---|
| A | `Symbol` | Human trading symbol (`NIFTY 50`, `RELIANCE`) |
| B | `Instrument Key` | Upstox internal key (`NSE_INDEX\|Nifty 50`) |
| C | **`LTP`** | Last Traded Price |
| D | `Change` | Point change from previous close |
| E | **`VWAP`** | Volume Weighted Average Price (ATP) |
| F | **`Open`** | Day Opening Price |
| G | **`High`** | Day High Price |
| H | **`Low`** | Day Low Price |
| I | **`Close`** | Previous Day Close Price |
| J | `Volume` | Total Day Volume |
| K | `Updated At` | Timestamp of last received tick |

---

## Universal Live Feed Server (Local HTTP)

When running, the bridge hosts an embedded HTTP feed at `http://127.0.0.1:8080/`:
- **Live CSV**: `http://127.0.0.1:8080/live.csv`
- **Live JSON**: `http://127.0.0.1:8080/live.json`
- **Single Quote**: `http://127.0.0.1:8080/quote/NIFTY 50`

In Microsoft Excel or LibreOffice Calc on any operating system, you can fetch live quotes directly using:
```excel
=WEBSERVICE("http://127.0.0.1:8080/quote/NIFTY 50")
```
