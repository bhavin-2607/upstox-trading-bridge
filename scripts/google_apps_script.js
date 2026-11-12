/**
 * ==============================================================================
 * UPSTOX LIVE MARKET DATA GOOGLE APPS SCRIPT WEBHOOK (Zero GCP Setup)
 * High-Performance Optimized Version (Sub-Second Execution, No Read Timeouts)
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
      var aData = payload.a_data;     // Col A: [SCRIPT] clean normal symbols (optional)
      var cgData = payload.cg_data;   // Cols C to G: [LTP, OPEN, HIGH, LOW, P.CLOSE]
      var yzData = payload.yz_data;   // Cols Y to Z: [P HIGH, P. LOW] (optional)
      var volData = payload.vol_data; // Col AF: [vol] (optional)

      var updatedRows = 0;

      // 1. In-place update script names in Col A (only when changed/requested)
      if (aData && aData.length > 0) {
        sheet.getRange(startRow, 1, aData.length, 1).setValues(aData);
      }

      // 2. In-place update live price columns C to G (5 contiguous columns)
      if (cgData && cgData.length > 0) {
        var numRows = cgData.length;
        sheet.getRange(startRow, 3, numRows, 5).setValues(cgData);
        updatedRows = numRows;
      }

      // 3. In-place update previous day high/low columns Y to Z (only when changed/requested)
      if (yzData && yzData.length > 0) {
        sheet.getRange(startRow, 25, yzData.length, 2).setValues(yzData);
      }

      // 4. In-place update volume column AF (Col 32)
      if (volData && volData.length > 0) {
        sheet.getRange(startRow, 32, volData.length, 1).setValues(volData);
      }

      // 5. Read current scripts from Column A for Bidirectional Sync (if requested)
      var currentScripts = [];
      if (payload.sync_scripts) {
        var lastRow = sheet.getLastRow();
        if (lastRow >= startRow) {
          var colAVals = sheet.getRange(startRow, 1, lastRow - startRow + 1, 1).getValues();
          for (var i = 0; i < colAVals.length; i++) {
            var val = colAVals[i][0];
            if (val !== null && val !== undefined && String(val).trim() !== "") {
              currentScripts.push([startRow + i, String(val).trim()]);
            }
          }
        }
      }

      return ContentService.createTextOutput(JSON.stringify({
        status: "success",
        mode: "bst",
        sheet: targetSheetName,
        rows_updated: updatedRows,
        scripts: currentScripts,
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
