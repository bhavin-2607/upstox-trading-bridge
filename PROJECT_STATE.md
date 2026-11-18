# BSA Trading Bridge - Project Context & State

> **Last Updated**: 2026-11-18  
> **Previous Session ID**: `4a66ba61-00ab-4850-a9cc-f214e09f8633`  
> **Repository**: `~/Projects/upstox-trading-bridge`

---

## 1. Project Overview & Architecture
**BSA Trading Bridge** is a low-latency, real-time algorithmic market data engine designed to stream Upstox live ticks directly into:
1. **Active Microsoft Excel Workbook (`trial.xlsx`)** via high-speed COM/`xlwings` batch slicing.
2. **Cloud Google Sheets (`BST`)** via Google Apps Script Webhook.

### Core Data Flow
- **Local Excel is the Calculation Engine**: Excel calculates all proprietary trading indicators (`TREND`, `MEN`, `GHAN`, `INTRA`, `SUPER`, `ENTRY`, `SL`, `TGT1/2/3`, `BT1/2/3`, `DIFF`, `ST1/2/3`, `VWAP`, `vol`, pivots, etc.) locally on your computer.
- **Google Sheets is the Public Display Terminal (Option 1 Formula Masking)**: Upstox Bridge extracts the **evaluated values** (`xw_sheet.value`) from Excel in ~15ms and writes them as plain numbers and signals (`BUY`/`SELL`) to Google Sheets.
- **Zero Formula Footprint**: No formulas (`=IF(...)`) exist in Google Sheets, ensuring clients/viewers cannot steal or reverse-engineer formulas.

---

## 2. Key Safeguards & Mechanisms

1. **Dual Google Sheets Publishing Modes**:
   - **Direct Raw Prices Mode (`publish_mode = "formulas"`)**: Pushes only live price columns (LTP, Open, High, Low, P.Close in Cols C-G, and Volume in Col AF) = ~1,482 cells. Extremely lightweight and updates in <1.5s. Ideal for direct connectivity and personal sheets with formulas already in place.
   - **Values-Only Formula Masking Mode (`publish_mode = "values"`)**: Pushes evaluated matrix (Columns B to AW) = ~11,856 cells. Protects proprietary formulas from public viewers. Protected by intelligent dirty-checking (skips 95% of unchanged ticks) and 35s HTTP timeout with connection pooling.
2. **Column A Immunity**:
   - Continuous live sync writes strictly to target data columns. Column A (`[SCRIPT]`) is never overwritten by price ticks, allowing users to type new scripts freely.
3. **Bidirectional Script Synchronization**:
   - Adding/editing in Google Sheet or Excel is dynamically detected and subscribed via Upstox live WebSocket feed.
4. **Zero-Lag Sound & Custom Price Alert Engine**:
   - Strictly user-specified custom target price alerts (Symbol + Target Price + Above/Below + Proximity Buffer).
   - In-memory tick evaluation (<0.01ms per tick) inside `MarketStore.update_quote()` without COM/Excel overhead.
   - 2-Stage Alert Lifecycle: `ACTIVE` -> `APPROACHING` (two-tone gentle chime) -> `TRIGGERED` (bright bell chime).
   - Non-blocking asynchronous audio (`winsound.SND_ASYNC` on Windows, bounded queue `maxsize=1`, 1.2s debounce).
   - No automatic signal monitoring across all 247 scripts, eliminating CPU stutter and Windows PC lag.
5. **Resilient Network & GUI Architecture**:
   - Settings dialog features a permanently pinned bottom footer (`Save Changes` & `Cancel`) and scrollable container.
   - HTTP session pooling (`requests.Session`) and exponential backoff prevent Google Apps Script queue saturation.
   - Dedicated "Price Alerts & Bell Sound Manager" modal dialog and System Tray menu integration.

---

## 3. Key Files Map

| File | Purpose |
| :--- | :--- |
| `upstox_bridge/core/alert_engine.py` | Custom target price alert engine, 2-stage lifecycle, JSON persistence |
| `upstox_bridge/core/sound_engine.py` | Ultra-lightweight, non-blocking asynchronous audio engine (synthesized WAVs) |
| `upstox_bridge/gui/alerts_dialog.py` | Modern CustomTkinter modal dialog for custom alerts & sound manager |
| `upstox_bridge/destinations/bst_syncer.py` | In-place Excel syncer (`xlwings` + `openpyxl` fallback), evaluated matrix extractor |
| `upstox_bridge/destinations/gsheet_webhook.py` | Google Apps Script webhook integration, slice & matrix pusher |
| `scripts/google_apps_script.js` | Google Apps Script webhook endpoint for Google Sheets |
| `upstox_bridge/gui/settings_dialog.py` | Settings GUI with formula masking toggle and restore action |
| `upstox_bridge/core/config.py` | Application configuration & `.env` manager |
| `templates/BST_Master_Template.xlsx` | Master template with 232 scripts, headers, and formulas |
| `dist/BSATradingBridge` | Standalone compiled executable |
| `tests/` | Complete 62-test automated unit test suite |

---

## 4. How to Resume This Session

- **Using Antigravity CLI (`agy`)**:
  ```bash
  cd ~/Projects/upstox-trading-bridge
  agy --conversation 4a66ba61-00ab-4850-a9cc-f214e09f8633
  ```
- **Using Antigravity Desktop 2.0 / IDE**:
  - Open project folder `~/Projects/upstox-trading-bridge`.
  - In a chat, type `@` and mention conversation `4a66ba61-00ab-4850-a9cc-f214e09f8633` or reference this `PROJECT_STATE.md` file.
