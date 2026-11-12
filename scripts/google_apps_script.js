/**
 * ==============================================================================
 * UPSTOX LIVE MARKET DATA GOOGLE APPS SCRIPT WEBHOOK (Zero GCP Setup)
 * Supports both:
 * 1. Standard LiveMarket table mode (with header styling & full table sync)
 * 2. In-Place BST Sheet mode (updates LTP, OPEN, HIGH, LOW, P.CLOSE, P HIGH, P. LOW, vol
 *    without touching ANY formulas in columns B, H-X, AA-AE, AG-AQ)
 * ==============================================================================
 *
 * HOW TO UPDATE IN GOOGLE APPS SCRIPT:
 * 1. Open your target Google Sheet.
 * 2. In top menu, click: Extensions -> Apps Script.
 * 3. Replace all existing code with THIS entire script.
 * 4. Click Save (Cmd+S or floppy icon).
 * 5. Click "Deploy" (top right) -> "Manage deployments" -> Click Edit (pencil icon).
 * 6. Under Version, select "New version" -> Click "Deploy".
 */

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return ContentService.createTextOutput(JSON.stringify({
        status: "error",
        message: "No post data received"
      })).setMimeType(ContentService.MimeType.JSON);
    }

    var payload = JSON.parse(e.postData.contents);
    var targetSheetName = payload.sheet_name || "LiveMarket";
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName(targetSheetName);

    // If sheet doesn't exist yet, create it
    if (!sheet) {
      sheet = ss.insertSheet(targetSheetName);
    }

    // ========================================================================
    // MODE 1: BST Custom Trading Sheet In-Place Updates (Zero Formula Damage)
    // ========================================================================
    if (payload.mode === "bst") {
      var startRow = payload.start_row || 3;
      var cgData = payload.cg_data;   // Cols C to G: [LTP, OPEN, HIGH, LOW, P.CLOSE]
      var yzData = payload.yz_data;   // Cols Y to Z: [P HIGH, P. LOW]
      var volData = payload.vol_data; // Col AF: [vol]

      var updatedRows = 0;

      // 1. In-place update price columns C to G (5 contiguous columns)
      if (cgData && cgData.length > 0) {
        var numRows = cgData.length;
        sheet.getRange(startRow, 3, numRows, 5).setValues(cgData);
        sheet.getRange(startRow, 3, numRows, 5).setNumberFormat("#,##0.00");
        updatedRows = numRows;
      }

      // 2. In-place update previous day high/low columns Y to Z (2 contiguous columns)
      if (yzData && yzData.length > 0) {
        sheet.getRange(startRow, 25, yzData.length, 2).setValues(yzData);
        sheet.getRange(startRow, 25, yzData.length, 2).setNumberFormat("#,##0.00");
      }

      // 3. In-place update volume column AF (Col 32)
      if (volData && volData.length > 0) {
        sheet.getRange(startRow, 32, volData.length, 1).setValues(volData);
        sheet.getRange(startRow, 32, volData.length, 1).setNumberFormat("#,##0");
      }

      return ContentService.createTextOutput(JSON.stringify({
        status: "success",
        mode: "bst",
        sheet: targetSheetName,
        rows_updated: updatedRows,
        timestamp: new Date().toISOString()
      })).setMimeType(ContentService.MimeType.JSON);
    }

    // ========================================================================
    // MODE 2: Standard Live Watchlist Table Mode
    // ========================================================================
    var rows = payload.data;
    if (!rows || rows.length === 0) {
      return ContentService.createTextOutput(JSON.stringify({
        status: "ok",
        message: "Empty payload, nothing to update"
      })).setMimeType(ContentService.MimeType.JSON);
    }

    var numRows = rows.length;
    var numCols = rows[0].length;

    // Clear old rows/duplicates completely for standard table
    sheet.clearContents();

    // Write all live data atomically in one batch
    var range = sheet.getRange(1, 1, numRows, numCols);
    range.setValues(rows);

    // Header styling
    var headerRange = sheet.getRange(1, 1, 1, numCols);
    headerRange.setBackground("#1E293B"); // Slate dark
    headerRange.setFontColor("#FFFFFF");
    headerRange.setFontWeight("bold");
    headerRange.setHorizontalAlignment("center");

    // Number formatting for data rows (LTP, Change, VWAP, Open, High, Low, Close)
    if (numRows > 1) {
      sheet.getRange(2, 3, numRows - 1, 7).setNumberFormat("#,##0.00");
      sheet.getRange(2, 10, numRows - 1, 1).setNumberFormat("#,##0");
      sheet.getRange(2, 1, numRows - 1, 2).setHorizontalAlignment("left");
      sheet.getRange(2, 3, numRows - 1, 8).setHorizontalAlignment("right");
      sheet.getRange(2, 11, numRows - 1, 1).setHorizontalAlignment("center");
    }

    return ContentService.createTextOutput(JSON.stringify({
      status: "success",
      mode: "standard",
      rows_updated: numRows,
      timestamp: new Date().toISOString()
    })).setMimeType(ContentService.MimeType.JSON);

  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({
      status: "error",
      error: error.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
}

// Verification GET test endpoint
function doGet(e) {
  return ContentService.createTextOutput(JSON.stringify({
    status: "online",
    message: "Upstox Live Market Data Webhook is active and listening for POST requests!"
  })).setMimeType(ContentService.MimeType.JSON);
}
