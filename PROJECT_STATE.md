# BSA Trading Bridge - Project Context & State

> **Last Updated**: 2026-11-17  
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

1. **Column A Immunity**:
   - Continuous 3-second live price matrix sync (`bst_matrix`) writes strictly to **Columns 2 to 49 (Columns B to AW)**.
   - Column A (`[SCRIPT]`) is **never touched or overwritten** by live ticks, allowing users to type new scripts or edit Column A without interference.
2. **Bidirectional Script Synchronization**:
   - **Adding/Editing in Google Sheet**: Scanning runs every ~9s (`sync_scripts: true`). Google Apps Script reads Column A *first* before any cell writes, forwards the new script to Python, which adds it to Excel, subscribes to Upstox, and streams live prices.
   - **Adding/Editing in Excel**: Detected by `scan_scripts()`, updates Upstox subscriptions, and sends `a_data` to Google Sheet.
   - **Deletion Handling**: Removing a script from either Excel or Google Sheet clears the row without causing resurrection loops.
3. **Master Template & Self-Healing Restore**:
   - `templates/BST_Master_Template.xlsx` contains the pristine 232-script layout with all formulas.
   - Restore via GUI: Settings > "⚡️ Restore BST Template to Google Sheet".
   - Restore via CLI: `python main.py restore-gsheet --mode values`.

---

## 3. Key Files Map

| File | Purpose |
| :--- | :--- |
| `upstox_bridge/destinations/bst_syncer.py` | In-place Excel syncer (`xlwings` + `openpyxl` fallback), evaluated matrix extractor |
| `upstox_bridge/destinations/gsheet_webhook.py` | Google Apps Script webhook integration, slice & matrix pusher |
| `scripts/google_apps_script.js` | Google Apps Script webhook endpoint for Google Sheets |
| `upstox_bridge/gui/settings_dialog.py` | Settings GUI with formula masking toggle and restore action |
| `upstox_bridge/core/config.py` | Application configuration & `.env` manager |
| `templates/BST_Master_Template.xlsx` | Master template with 232 scripts, headers, and formulas |
| `dist/BSATradingBridge` | Standalone compiled executable |
| `tests/` | Complete 45-test automated unit test suite |

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
