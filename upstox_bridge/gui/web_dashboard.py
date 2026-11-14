"""Modern Web Dashboard for Upstox Live Market Data Bridge.

Provides a cross-platform, zero-dependency browser-based dashboard that works
on all operating systems (Mac, Windows, Linux) without requiring Tkinter.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from typing import Optional

from upstox_bridge.core.config import settings, update_env_variable
from upstox_bridge.core.logger import get_gui_logs, setup_production_logging
from upstox_bridge.runner import BridgeRunner

logger = logging.getLogger("WebDashboard")


class ThreadedDashboardServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP server for web dashboard."""
    daemon_threads = True


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Upstox Live Trading Bridge</title>
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: #151d2e;
      --card-border: #23314d;
      --text: #f1f5f9;
      --text-muted: #94a3b8;
      --primary: #38bdf8;
      --primary-hover: #0ea5e9;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --purple: #a855f7;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 24px;
    }
    .container { max-width: 1200px; margin: 0 auto; }
    
    /* Header */
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--card-border);
    }
    .brand h1 { font-size: 24px; font-weight: 700; color: #fff; display: flex; align-items: center; gap: 8px; }
    .brand p { color: var(--text-muted); font-size: 13px; margin-top: 2px; }
    .header-actions { display: flex; gap: 10px; align-items: center; }

    /* Button Styles */
    .btn {
      font-size: 14px;
      font-weight: 600;
      padding: 10px 18px;
      border-radius: 8px;
      border: none;
      cursor: pointer;
      transition: all 0.2s ease;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .btn-success { background: #059669; color: #fff; }
    .btn-success:hover { background: #047857; }
    .btn-purple { background: #9333ea; color: #fff; }
    .btn-purple:hover { background: #7e22ce; }
    .btn-danger { background: #dc2626; color: #fff; }
    .btn-danger:hover { background: #b91c1c; }
    .btn-secondary { background: var(--card-border); color: #cbd5e1; }
    .btn-secondary:hover { background: #334566; color: #fff; }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; }

    /* Cards Grid */
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 20px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    }
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
    .card-title { font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); font-weight: 600; }
    .badge {
      font-size: 11px;
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 20px;
      text-transform: uppercase;
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }
    .badge-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
    .badge-online { background: rgba(16, 185, 129, 0.15); color: var(--success); }
    .badge-online .badge-dot { background: var(--success); box-shadow: 0 0 8px var(--success); }
    .badge-waiting { background: rgba(245, 158, 11, 0.15); color: var(--warning); }
    .badge-waiting .badge-dot { background: var(--warning); }
    .badge-offline { background: rgba(239, 68, 68, 0.15); color: var(--danger); }
    .badge-offline .badge-dot { background: var(--danger); }
    .metric-value { font-size: 26px; font-weight: 700; color: #fff; margin-bottom: 6px; }
    .metric-sub { font-size: 12px; color: var(--text-muted); }

    /* Section Tabs / Panels */
    .section-title { font-size: 16px; font-weight: 600; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; }

    /* Tables */
    .table-container {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      overflow: hidden;
      margin-bottom: 24px;
      max-height: 380px;
      overflow-y: auto;
    }
    table { width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }
    th {
      background: #1a2438;
      color: var(--text-muted);
      font-weight: 600;
      padding: 12px 16px;
      position: sticky;
      top: 0;
      z-index: 10;
      border-bottom: 1px solid var(--card-border);
    }
    td { padding: 10px 16px; border-bottom: 1px solid rgba(35, 49, 77, 0.5); }
    tr:hover td { background: rgba(56, 189, 248, 0.04); }
    .price-up { color: var(--success); font-weight: 600; }
    .price-down { color: var(--danger); font-weight: 600; }

    /* Console / Logs */
    .console {
      background: #070a10;
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 16px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 12px;
      height: 220px;
      overflow-y: auto;
      color: #94a3b8;
    }
    .log-line { margin-bottom: 4px; line-height: 1.4; word-break: break-all; }
    .log-info { color: #cbd5e1; }
    .log-warn { color: var(--warning); }
    .log-error { color: var(--danger); }

    /* Modal */
    .modal-overlay {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.7);
      backdrop-filter: blur(4px);
      z-index: 100;
      align-items: center;
      justify-content: center;
    }
    .modal {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      width: 90%;
      max-width: 540px;
      padding: 24px;
      box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
    }
    .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
    .modal-title { font-size: 18px; font-weight: 700; color: #fff; }
    .modal-close { background: none; border: none; color: var(--text-muted); font-size: 22px; cursor: pointer; }
    .form-group { margin-bottom: 16px; }
    .form-label { display: block; font-size: 13px; font-weight: 600; color: #cbd5e1; margin-bottom: 6px; }
    .form-input {
      width: 100%;
      background: #0c121e;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 10px 14px;
      color: #fff;
      font-size: 13px;
      outline: none;
      transition: border-color 0.2s;
    }
    .form-input:focus { border-color: var(--primary); }
    .form-help { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
    .modal-footer { display: flex; justify-content: flex-end; gap: 10px; margin-top: 24px; }

    /* Notification toast */
    .toast {
      position: fixed;
      bottom: 24px;
      right: 24px;
      padding: 12px 20px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      z-index: 200;
      display: none;
      animation: fadeIn 0.3s ease;
    }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <h1><span>⚡</span> Upstox Live Trading Bridge</h1>
        <p>Real-time Market Streamer for Excel (BST / Trial) & Google Sheets</p>
      </div>
      <div class="header-actions">
        <button id="btn-start-live" class="btn btn-success" onclick="startBridge('live')">▶ Start Live Feed</button>
        <button id="btn-start-sim" class="btn btn-purple" onclick="startBridge('simulate')">⚗ Start Simulation</button>
        <button id="btn-stop" class="btn btn-danger" onclick="stopBridge()" disabled>■ Stop</button>
        <button class="btn btn-secondary" onclick="openSettings()">⚙ Settings</button>
      </div>
    </header>

    <!-- Telemetry Cards -->
    <div class="grid">
      <!-- Market Feed Card -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">Market Feed Streamer</span>
          <span id="feed-badge" class="badge badge-offline"><span class="badge-dot"></span> Offline</span>
        </div>
        <div id="feed-ticks" class="metric-value">0 Ticks</div>
        <div id="feed-symbols" class="metric-sub">0 instruments subscribed</div>
      </div>

      <!-- Excel BST Syncer Card -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">Excel BST Syncer</span>
          <span id="excel-badge" class="badge badge-offline"><span class="badge-dot"></span> Disconnected</span>
        </div>
        <div id="excel-file" class="metric-value" style="font-size: 18px; word-break: break-all;">bst.xlsx</div>
        <div id="excel-sub" class="metric-sub">Sheet: BST | Last sync: Never</div>
      </div>

      <!-- Google Sheets Card -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">Google Sheets Sync</span>
          <span id="gsheet-badge" class="badge badge-offline"><span class="badge-dot"></span> Inactive</span>
        </div>
        <div id="gsheet-status" class="metric-value" style="font-size: 18px;">Disabled</div>
        <div id="gsheet-sub" class="metric-sub">Webhook sync cycle: 3.0s</div>
      </div>
    </div>

    <!-- Live Watchlist Table -->
    <div class="section-title">
      <span>Live Market Quotes (<span id="table-count">0</span>)</span>
      <input type="text" id="filter-input" placeholder="Filter symbol..." oninput="renderTable()" style="background: #151d2e; border: 1px solid var(--card-border); padding: 6px 12px; border-radius: 6px; color: #fff; font-size: 12px; width: 180px;">
    </div>
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>LTP (₹)</th>
            <th>High (₹)</th>
            <th>Low (₹)</th>
            <th>Close (₹)</th>
            <th>Volume</th>
            <th>Updated</th>
          </tr>
        </thead>
        <tbody id="quotes-tbody">
          <tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 32px;">No live quotes received yet. Click 'Start Live Feed' or 'Start Simulation'.</td></tr>
        </tbody>
      </table>
    </div>

    <!-- Console / Live Logs -->
    <div class="section-title">
      <span>Activity Logs</span>
      <button class="btn btn-secondary" onclick="clearLogs()" style="padding: 4px 10px; font-size: 11px;">Clear Logs</button>
    </div>
    <div id="console-logs" class="console">
      <div class="log-line log-info">System initialized. Ready to connect.</div>
    </div>
  </div>

  <!-- Settings Modal -->
  <div id="settings-modal" class="modal-overlay">
    <div class="modal">
      <div class="modal-header">
        <h3 class="modal-title">Bridge Configuration</h3>
        <button class="modal-close" onclick="closeSettings()">&times;</button>
      </div>

      <div class="form-group">
        <label class="form-label">Upstox Access Token</label>
        <input type="password" id="input-token" class="form-input" placeholder="Paste today's access_token here">
        <p class="form-help">Saved directly into .env (No API key / secret required).</p>
      </div>

      <div class="form-group">
        <label class="form-label">Excel Workbook Path</label>
        <input type="text" id="input-excel" class="form-input" placeholder="bst.xlsx">
        <p class="form-help">Automatically searches for bst.xlsx or trial.xlsx.</p>
      </div>

      <div class="form-group">
        <label class="form-label">Google Sheet Webhook URL</label>
        <input type="text" id="input-webhook" class="form-input" placeholder="https://script.google.com/macros/s/.../exec">
        <div style="margin-top: 8px;">
          <button class="btn btn-secondary" onclick="testWebhook()" style="padding: 6px 12px; font-size: 12px;">🔗 Test Connection</button>
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn btn-secondary" onclick="closeSettings()">Cancel</button>
        <button class="btn btn-success" onclick="saveSettings()">Save & Apply</button>
      </div>
    </div>
  </div>

  <div id="toast" class="toast"></div>

  <script>
    let quotesData = {};
    let isRunning = false;

    function showToast(msg, isError = false) {
      const toast = document.getElementById("toast");
      toast.innerText = msg;
      toast.style.background = isError ? "#dc2626" : "#059669";
      toast.style.color = "#fff";
      toast.style.display = "block";
      setTimeout(() => { toast.style.display = "none"; }, 3500);
    }

    async function fetchStatus() {
      try {
        const res = await fetch("/api/status");
        if (!res.ok) return;
        const d = await res.json();
        isRunning = d.running;

        // Update Buttons
        document.getElementById("btn-start-live").disabled = isRunning;
        document.getElementById("btn-start-sim").disabled = isRunning;
        document.getElementById("btn-stop").disabled = !isRunning;

        // Feed Badge
        const feedBadge = document.getElementById("feed-badge");
        if (d.running) {
          feedBadge.className = "badge badge-online";
          feedBadge.innerHTML = '<span class="badge-dot"></span> ' + (d.simulation ? "Simulation" : "Connected");
        } else {
          feedBadge.className = "badge badge-offline";
          feedBadge.innerHTML = '<span class="badge-dot"></span> Offline';
        }
        document.getElementById("feed-ticks").innerText = `${d.ticks.toLocaleString()} Ticks`;
        document.getElementById("feed-symbols").innerText = `${d.symbols_count} instruments subscribed`;

        // Excel Badge
        const excelBadge = document.getElementById("excel-badge");
        if (d.excel_status === "Connected") {
          excelBadge.className = "badge badge-online";
          excelBadge.innerHTML = '<span class="badge-dot"></span> Connected';
        } else if (d.excel_status.includes("Edit") || d.excel_status.includes("Waiting")) {
          excelBadge.className = "badge badge-waiting";
          excelBadge.innerHTML = '<span class="badge-dot"></span> ' + d.excel_status;
        } else {
          excelBadge.className = "badge badge-offline";
          excelBadge.innerHTML = '<span class="badge-dot"></span> ' + d.excel_status;
        }
        document.getElementById("excel-file").innerText = d.excel_file || "bst.xlsx";
        document.getElementById("excel-sub").innerText = `Sheet: ${d.sheet_name} | Last sync: ${d.last_sync || 'Never'}`;

        // Google Sheets Badge
        const gsheetBadge = document.getElementById("gsheet-badge");
        if (d.gsheet_status && d.gsheet_status.startsWith("Active")) {
          gsheetBadge.className = "badge badge-online";
          gsheetBadge.innerHTML = '<span class="badge-dot"></span> Active';
          document.getElementById("gsheet-status").innerText = d.gsheet_status;
        } else {
          gsheetBadge.className = "badge badge-offline";
          gsheetBadge.innerHTML = '<span class="badge-dot"></span> ' + (d.gsheet_status || "Disabled");
          document.getElementById("gsheet-status").innerText = d.gsheet_status || "Disabled";
        }
      } catch (e) {
        console.error("Status poll error:", e);
      }
    }

    async function fetchQuotes() {
      try {
        const res = await fetch("/api/quotes");
        if (!res.ok) return;
        quotesData = await res.json();
        renderTable();
      } catch (e) {}
    }

    function renderTable() {
      const tbody = document.getElementById("quotes-tbody");
      const filter = document.getElementById("filter-input").value.toUpperCase();
      const keys = Object.keys(quotesData);
      document.getElementById("table-count").innerText = keys.length;

      if (keys.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 32px;">No quotes yet. Click \'Start Live Feed\' or \'Start Simulation\'.</td></tr>';
        return;
      }

      let html = "";
      for (const sym of keys) {
        if (filter && !sym.toUpperCase().includes(filter)) continue;
        const q = quotesData[sym];
        const ltp = q.ltp ? q.ltp.toFixed(2) : "-";
        const high = q.high ? q.high.toFixed(2) : "-";
        const low = q.low ? q.low.toFixed(2) : "-";
        const close = q.close ? q.close.toFixed(2) : "-";
        const vol = q.volume ? q.volume.toLocaleString() : "-";
        const ts = q.timestamp || "-";

        html += `<tr>
          <td style="font-weight: 600; color: #fff;">${sym}</td>
          <td class="price-up" style="font-size: 14px;">${ltp}</td>
          <td>${high}</td>
          <td>${low}</td>
          <td>${close}</td>
          <td>${vol}</td>
          <td style="color: var(--text-muted);">${ts}</td>
        </tr>`;
      }
      tbody.innerHTML = html;
    }

    async function fetchLogs() {
      try {
        const res = await fetch("/api/logs");
        if (!res.ok) return;
        const data = await res.json();
        const box = document.getElementById("console-logs");
        if (data.logs && data.logs.length > 0) {
          box.innerHTML = data.logs.map(line => {
            let cls = "log-info";
            if (line.includes("WARNING")) cls = "log-warn";
            else if (line.includes("ERROR") || line.includes("Exception")) cls = "log-error";
            return `<div class="log-line ${cls}">${escapeHtml(line)}</div>`;
          }).join("");
          box.scrollTop = box.scrollHeight;
        }
      } catch (e) {}
    }

    function escapeHtml(text) {
      return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    async function startBridge(mode) {
      try {
        showToast(mode === 'live' ? "Starting Live Feed..." : "Starting Simulation...");
        const res = await fetch("/api/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode })
        });
        const d = await res.json();
        if (d.success) {
          showToast(d.message);
        } else {
          showToast(d.error || "Failed to start", true);
        }
      } catch (e) {
        showToast("Error starting bridge: " + e, true);
      }
    }

    async function stopBridge() {
      try {
        showToast("Stopping bridge...");
        const res = await fetch("/api/stop", { method: "POST" });
        const d = await res.json();
        showToast(d.message);
      } catch (e) {
        showToast("Error stopping: " + e, true);
      }
    }

    function clearLogs() {
      document.getElementById("console-logs").innerHTML = "";
    }

    function openSettings() {
      document.getElementById("settings-modal").style.display = "flex";
      fetch("/api/settings").then(r => r.json()).then(d => {
        document.getElementById("input-excel").value = d.excel_file || "bst.xlsx";
        document.getElementById("input-webhook").value = d.webhook_url || "";
      });
    }

    function closeSettings() {
      document.getElementById("settings-modal").style.display = "none";
    }

    async function saveSettings() {
      const token = document.getElementById("input-token").value.trim();
      const excel = document.getElementById("input-excel").value.trim();
      const webhook = document.getElementById("input-webhook").value.trim();

      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, excel, webhook })
      });
      const d = await res.json();
      if (d.success) {
        showToast("Settings saved successfully!");
        closeSettings();
      } else {
        showToast(d.error || "Failed to save settings", true);
      }
    }

    async function testWebhook() {
      showToast("Testing webhook connection...");
      const res = await fetch("/api/test-gsheet", { method: "POST" });
      const d = await res.json();
      if (d.success) {
        showToast("Webhook test passed: " + d.message);
      } else {
        showToast("Webhook test failed: " + (d.error || "Check URL"), true);
      }
    }

    // Polling intervals
    setInterval(fetchStatus, 1000);
    setInterval(fetchQuotes, 1000);
    setInterval(fetchLogs, 2000);
    fetchStatus();
    fetchLogs();
  </script>
</body>
</html>
"""


class WebDashboardHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for Web Dashboard UI and REST API."""

    runner: Optional[BridgeRunner] = None

    def log_message(self, format, *args):
        # Suppress routine GET logging to keep terminal tidy
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path in ("", "/dashboard", "/index.html"):
            self._send_html(200, DASHBOARD_HTML)

        elif path == "/api/status":
            r = self.runner
            data = {
                "running": r.is_running if r else False,
                "simulation": r.is_simulation if r else False,
                "ticks": r.ticks_received if r else 0,
                "symbols_count": r.market_store.count() if r else 0,
                "feed_state": r.streamer.state if (r and r.streamer) else "Disconnected",
                "excel_status": r.excel_status if r else "Disconnected",
                "excel_file": r.excel_file.name if r else "bst.xlsx",
                "sheet_name": r.sheet_name if r else "BST",
                "last_sync": time.strftime("%H:%M:%S", time.localtime(r.bst_syncer.last_sync_time)) if (r and r.bst_syncer and r.bst_syncer.last_sync_time) else "",
                "gsheet_status": r.gsheet_status if r else "Disabled",
            }
            self._send_json(200, data)

        elif path == "/api/quotes":
            r = self.runner
            quotes = {}
            if r and r.market_store:
                for sym, q in r.market_store.get_all_quotes_dict().items():
                    quotes[sym] = {
                        "ltp": q.get("ltp"),
                        "high": q.get("high"),
                        "low": q.get("low"),
                        "close": q.get("close"),
                        "volume": q.get("volume"),
                        "timestamp": q.get("timestamp", ""),
                    }
            self._send_json(200, quotes)

        elif path == "/api/logs":
            logs = get_gui_logs()
            self._send_json(200, {"logs": logs})

        elif path == "/api/settings":
            self._send_json(200, {
                "excel_file": str(settings.excel_file_path.name),
                "sheet_name": settings.excel_sheet_name,
                "webhook_url": settings.gsheet_webhook_url or "",
            })

        else:
            self._send_json(404, {"error": "Not Found"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}

        if path == "/api/start":
            mode = payload.get("mode", "live")
            r = self.runner
            if not r:
                self._send_json(500, {"error": "Runner not initialized"})
                return

            if r.is_running:
                self._send_json(400, {"error": "Bridge is already running."})
                return

            def _start_worker():
                try:
                    if mode == "simulate":
                        r.start_simulation_services()
                    else:
                        r.start_services(interactive_login_if_needed=False)
                except Exception as e:
                    logger.error(f"Error starting bridge: {e}")

            t = threading.Thread(target=_start_worker, daemon=True)
            t.start()
            self._send_json(200, {"success": True, "message": f"{mode.capitalize()} mode started."})

        elif path == "/api/stop":
            r = self.runner
            if r and r.is_running:
                r.stop()
                self._send_json(200, {"success": True, "message": "Bridge stopped successfully."})
            else:
                self._send_json(200, {"success": True, "message": "Bridge was not running."})

        elif path == "/api/settings":
            token = payload.get("token", "").strip()
            excel = payload.get("excel", "").strip()
            webhook = payload.get("webhook", "").strip()

            try:
                if token:
                    update_env_variable("UPSTOX_ACCESS_TOKEN", token)
                    settings.reload()
                    logger.info("Updated UPSTOX_ACCESS_TOKEN in .env")

                if excel:
                    update_env_variable("EXCEL_FILE_PATH", excel)
                    settings.reload()
                    logger.info(f"Updated EXCEL_FILE_PATH to {excel}")

                if webhook:
                    update_env_variable("GSHEET_WEBHOOK_URL", webhook)
                    settings.reload()
                    logger.info("Updated GSHEET_WEBHOOK_URL in .env")

                self._send_json(200, {"success": True, "message": "Settings updated."})
            except Exception as e:
                self._send_json(500, {"error": str(e)})

        elif path == "/api/test-gsheet":
            webhook_url = settings.gsheet_webhook_url
            if not webhook_url:
                self._send_json(400, {"error": "No GSHEET_WEBHOOK_URL configured in .env."})
                return

            try:
                import requests
                payload = {
                    "mode": "test",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "cg_data": [[100.0, 105.0, 95.0, 98.0, 102.0]],
                }
                res = requests.post(webhook_url, json=payload, timeout=8.0)
                if res.status_code == 200:
                    self._send_json(200, {"success": True, "message": f"Webhook returned HTTP 200: {res.text[:80]}"})
                else:
                    self._send_json(res.status_code, {"error": f"HTTP {res.status_code}: {res.text[:80]}"})
            except Exception as e:
                self._send_json(500, {"error": str(e)})

        else:
            self._send_json(404, {"error": "Not Found"})

    def _send_html(self, status: int, html: str):
        data = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def launch_web_dashboard(
    host: str = "127.0.0.1",
    port: int = 8080,
    open_browser: bool = True,
    runner: Optional[BridgeRunner] = None,
):
    """Launch the Web Dashboard HTTP server and open browser."""
    setup_production_logging()

    if runner is None:
        runner = BridgeRunner()

    WebDashboardHandler.runner = runner

    # Try binding to configured port, fallback to port+1 if busy
    server = None
    active_port = port
    for p in range(port, port + 10):
        try:
            server = ThreadedDashboardServer((host, p), WebDashboardHandler)
            active_port = p
            break
        except OSError:
            continue

    if not server:
        logger.error(f"Could not bind Web Dashboard to {host}:{port}-{port+10}")
        return

    url = f"http://{host}:{active_port}/dashboard"
    print("\n" + "=" * 70)
    print("       UPSTOX TRADING BRIDGE - WEB DASHBOARD")
    print("=" * 70)
    print(f"  [OK] Dashboard Server active at: {url}")
    print("  Controls available: Live Streaming, Simulation, Settings, Logs")
    print("  Press Ctrl+C in this terminal at any time to safely exit.")
    print("=" * 70 + "\n")

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Web Dashboard...")
    finally:
        if runner.is_running:
            runner.stop()
        server.shutdown()
        server.server_close()
        print("Web Dashboard closed.")
