# Upstox Trading Bridge — UI/UX Improvement Proposal
**Author**: Senior UI/UX & Product Design Specialist  
**Application**: Upstox Live Market Data Bridge (Desktop Edition)  
**Target Audience**: Algorithmic & Discretionary Day Traders, Scalpers, Commodity Traders  
**Date**: November 2026  

---

## 1. Executive Summary & Design Philosophy

Financial trading tools operate in high-stress, time-sensitive environments where visual ambiguity directly translates to financial risk. The primary objective of the Upstox Bridge UI is not merely aesthetic elegance, but **sub-second situational awareness, zero visual noise, and instantaneous feedback**.

The current application provides a solid technical foundation (CustomTkinter dark theme, high-contrast status cards, and responsive controls). However, it currently functions primarily as an "engine monitor" rather than a **cohesive trader cockpit**. Traders still experience friction having to switch back and forth between Excel, Google Sheets, and the app just to verify a quote or add a new option contract.

This proposal details concrete, actionable enhancements to transform the application into an **industry-grade, high-performance financial workstation utility**.

---

## 2. Heuristic Evaluation & Current Pain Points

| UX Area | Current State | Friction / Risk | Proposed Solution |
| :--- | :--- | :--- | :--- |
| **Price Visibility** | Users must keep Excel or Google Sheets open to see if a symbol is streaming prices. | Traders have zero visual confirmation inside the app whether a newly added contract is actually ticking. | **Mini Live Ticker Strip**: A compact, interactive 6–8 symbol watchlist strip inside the app with real-time green/red price flash. |
| **Symbol Entry** | Users must open Excel, locate Column A, type the symbol, and save. | Slow and error-prone during live market hours. | **Quick-Add Omnibar**: Top search bar with auto-complete: type `NIFTY 26000 CE` and hit `Enter` to inject into Excel & Feed. |
| **Token Validity** | Token status is binary (either working or throws an error on connect). | Upstox tokens expire daily at 03:30 AM. Traders often find out their token expired after market opens. | **Token Health Pill**: Live badge showing remaining validity (e.g. `🟢 Token Active: 6h 40m remaining`) with 1-click renewal. |
| **Market Session** | Shows static label `"CLOSED"` outside regular equity hours. | Ignores MCX Commodity session (open till 23:30 / 23:55 IST) and NSE Pre-Open (09:00–09:08). | **Dynamic Market Clock**: Multi-exchange session banner (NSE Equity, F&O, MCX Commodity) with countdown timer. |
| **Log Drawer** | Raw technical logs dumped into a single text widget. | Clutters important alerts with background polling messages. | **Categorized Activity Feed**: Tabs for `[ All ] [ Market Ticks ] [ Excel Sync ] [ Alerts Only ]` with humanized messages. |
| **Number Jitter** | Standard variable-width UI font used for numbers. | Digits shift horizontally as prices tick, causing visual fatigue. | **Tabular Figures**: Switch to tabular monospaced numerical font (e.g., JetBrains Mono / SF Mono / Consolas). |

---

## 3. Proposed UI Wireframe & Architecture

```text
+---------------------------------------------------------------------------------------------------+
|  ⚡ UPSTOX TRADING BRIDGE  v2.0        [ NSE: Live 🟢 ]  [ MCX: Live 🟢 ]  [ Token: 7h 12m 🟢 ]   ⚙ |
+---------------------------------------------------------------------------------------------------+
|  [🔍 Quick Add Script: e.g. NIFTY 26000 CE, CRUDEOIL DEC FUT                ] [ + Add to Sheet ] |
+---------------------------------------------------------------------------------------------------+
|  TELEMETRY & SYSTEM HEALTH                                                                        |
|  +--------------------+  +--------------------+  +--------------------+  +--------------------+   |
|  | 📡 Market Feed     |  | 📊 Excel (BST)     |  | 🌐 Google Sheets   |  | ⚡ Throughput      |   |
|  | CONNECTED          |  | CONNECTED          |  | ACTIVE (3.0s)      |  | 42 ticks/sec       |   |
|  | 234 Instruments   |  | bst.xlsx [BST]     |  | Latency: 140ms     |  | Ping: 18ms         |   |
|  | 14,890 Ticks       |  | Sync: 18:45:12     |  | Last sent: 2s ago  |  | Memory: 64 MB      |   |
|  +--------------------+  +--------------------+  +--------------------+  +--------------------+   |
+---------------------------------------------------------------------------------------------------+
|  LIVE PINNED WATCHLIST (Auto-updating mini-strip)                                                 |
|  +------------------+  +------------------+  +------------------+  +------------------+           |
|  | NIFTY 50         |  | BANKNIFTY        |  | NIFTY 26000 CE   |  | GOLD DEC FUT     |           |
|  | 25,144.30 ▲+0.4% |  | 61,034.10 ▼-0.2% |  | 5.50 ▲+12.2%     |  | 136,705.00 ▲+0.8%|           |
|  | H: 25,246 L:25,054| | H: 61,300 L:60,780| | H: 14.35 L: 4.45 |  | H:137,587 L:136055|          |
|  +------------------+  +------------------+  +------------------+  +------------------+           |
+---------------------------------------------------------------------------------------------------+
|  PRIMARY CONTROLS                                                                                 |
|  [ ▶ START LIVE STREAM ]    [ ⚗ RUN SIMULATION ]    [ ■ STOP BRIDGE ]    [ 🔄 RELOAD EXCEL ]      |
+---------------------------------------------------------------------------------------------------+
|  ACTIVITY CONSOLE                                                                                 |
|  Tabs: (•) All Logs   ( ) Sync Events   ( ) Warnings & Errors          [ Clear ] [ Export Log ]   |
|  +---------------------------------------------------------------------------------------------+  |
|  | 18:45:12 [INFO] Subscribed to NIFTY 26000 CE (17 NOV 26). Baseline LTP: ₹5.50              |  |
|  | 18:45:13 [SUCCESS] Excel row 235 updated: [C:G] live price matrix written in 12ms.          |  |
|  | 18:45:15 [INFO] Google Sheets bidirectional sync: 234 rows confirmed.                      |  |
|  +---------------------------------------------------------------------------------------------+  |
+---------------------------------------------------------------------------------------------------+
```

---

## 4. Detailed Component Specifications

### 4.1 Header Bar & Market Context Clock
* **Multi-Segment Market Status Pills**:
  * **NSE Equity & F&O**: `09:15 – 15:30 IST` → Green pill `[ NSE: Live ]`; after 15:30 → Gray `[ NSE: Closed ]`.
  * **MCX Commodity**: `09:00 – 23:30 / 23:55 IST` → Shows green `[ MCX: Live ]` during evening commodity sessions even when NSE is closed.
* **Token Health & Expiry Counter**:
  * Decodes the JWT `exp` timestamp in `UPSTOX_ACCESS_TOKEN`.
  * Renders visual countdown:
    * `> 4 hours remaining`: Green badge `🟢 7h 24m`.
    * `< 2 hours remaining`: Amber warning `🟡 1h 45m`.
    * `Expired`: Red pulsating badge `🔴 Token Expired (Click to Renew)`.

### 4.2 Quick-Add Script Omnibar
* **Trader Problem**: Adding a new strike or commodity currently forces the trader to open Excel, scroll down, type the text, and wait for the watchdog.
* **UX Solution**:
  * Integrated single-line text entry at the top of the GUI.
  * Real-time autocomplete suggestions as the user types (e.g. typing `NIFTY 26000` suggests `NIFTY 26000 CE (17 Nov)` and `NIFTY 26000 PE (17 Nov)`).
  * Pressing `Enter` or clicking `+ Add` immediately:
    1. Finds the next empty row in Excel (`bst.xlsx`).
    2. Writes the clean symbol into Column A.
    3. Triggers immediate historical daily stat fetch (`P HIGH`, `P. LOW`, `P.CLOSE`).
    4. Subscribes to the live WebSocket feed.

### 4.3 Pinned Mini-Watchlist Strip
* Displays a horizontal scrollable row of 4–6 prominent cards:
  * Index benchmarks: `NIFTY 50`, `BANKNIFTY`.
  * User-specified pinned strikes or commodities: `GOLD DEC FUT`, `NIFTY 26000 CE`.
* **Micro-Interactions**:
  * Price changes trigger a **subtle 300ms background flash**: soft green (`#052e16`) on price tick up, soft red (`#3f1212`) on price tick down.
  * Displays Day High/Low progress bar showing current price relative to the daily range.

### 4.4 Tabular Figures (Typography & Motion)
* **Problem**: Standard sans-serif proportional fonts cause numbers like `1` and `8` to have different widths, causing table cells and price cards to vibrate/jitter when streaming fast ticks.
* **Solution**:
  * Apply tabular numerical formatting: `font-variant-numeric: tabular-nums` or standard monospace numbers (`JetBrains Mono`, `Consolas`, `Menlo`).
  * Smooth transition on status badge color changes (150ms ease).

### 4.5 Humanized Diagnostic Alerts
* Instead of technical COM error codes, translate internal statuses into clear trader language:
  * `0x80010001 (RPC_E_CALL_REJECTED)` → **"Excel paused: You are currently typing in a cell. Updates buffered."**
  * `Read timed out (script.google.com)` → **"Google Sheets busy; retrying sync in 3s."**
  * `UDAPI1221` → **"Using manual token from .env (IP restriction bypassed)."**

---

## 5. Implementation Roadmap

### Phase 1: High Impact, Low Effort (1–2 Days)
1. **Token Health Pill**: JWT expiration decoder in `upstox_bridge/auth/oauth.py` and display countdown badge in GUI header.
2. **Tabular Monospace Numerics**: Set numeric font in metric labels and log drawer.
3. **Multi-Segment Market Clock**: Distinguish NSE Equity (closes 15:30) vs MCX Commodity (open until 23:30/23:55).

### Phase 2: Medium Term Enhancements (3–4 Days)
1. **Quick-Add Omnibar**: Add symbol input widget with `InstrumentMaster.search_symbols()` autocomplete dropdown.
2. **Pinned Mini-Watchlist Strip**: 4-card live quote view inside the main window above controls.
3. **Log Filter Tabs**: Filter log view by System, Market Ticks, and Sync Errors.

### Phase 3: Advanced FinTech Features (Future)
1. **Desktop Native Notifications**: Configurable alerts (Windows Toast / macOS Notification Center) when a tracked instrument reaches its `P HIGH` or `P. LOW`.
2. **Option Chain Matrix**: Expandable modal showing live calls and puts around ATM for selected index.

---

## 6. Design System Color Tokens

| Token Name | Hex Code | Purpose |
| :--- | :--- | :--- |
| `bg-app` | `#0B0F19` | Deep slate-black canvas background |
| `card-surface` | `#151D2E` | Elevated component surface |
| `card-border` | `#23314D` | Subtle border separation |
| `text-primary` | `#F8FAFC` | Main metrics, prices, and symbols |
| `text-secondary` | `#94A3B8` | Labels, headers, timestamps |
| `status-bull` | `#10B981` | Uptick, live connection, success badge |
| `status-bear` | `#EF4444` | Downtick, disconnected, error state |
| `status-accent` | `#38BDF8` | Buttons, active tabs, highlights |
| `status-warning`| `#F59E0B` | Simulation mode, cell-edit lock, token expiry warning |
