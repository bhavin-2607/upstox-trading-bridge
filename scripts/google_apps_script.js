/**
 * ==============================================================================
 * BSA TRADING BRIDGE - GOOGLE APPS SCRIPT WEBHOOK (Zero GCP Setup)
 * High-Performance Market Data Syncer (Sub-Second In-Place Execution)
 * ==============================================================================
 *
 * HOW TO INSTALL / UPDATE IN GOOGLE APPS SCRIPT:
 * 1. Open your Google Sheet (e.g. BST Trading Sheet).
 * 2. In top menu, click: Extensions -> Apps Script.
 * 3. Replace all existing code with THIS entire script.
 * 4. Click Save (Cmd+S or floppy icon).
 * 5. Click "Deploy" (top right) -> "Manage deployments" -> Click Edit (pencil icon).
 * 6. Under Version, select "New version" -> Click "Deploy".
 * 7. Ensure access is set to: "Anyone" (so the desktop bridge can POST without OAuth).
 * ==============================================================================
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
    var targetSheetName = payload.sheet_name || "BST";
    var ss = SpreadsheetApp.getActiveSpreadsheet();

    // ========================================================================
    // MODE 0: Non-Destructive Connectivity Test (Zero Sheet Writes)
    // ========================================================================
    if (payload.mode === "ping" || payload.mode === "test") {
      return ContentService.createTextOutput(JSON.stringify({
        status: "success",
        mode: "ping",
        sheet: targetSheetName,
        message: "Google Sheet Webhook connection verified successfully (Zero sheet writes)."
      })).setMimeType(ContentService.MimeType.JSON);
    }

    // ========================================================================
    // MODE 1: BST Template Initialization & Formula Restoration
    // ========================================================================
    if (payload.mode === "init_bst" || payload.mode === "restore_bst") {
      var bstSheet = ss.getSheetByName(targetSheetName);
      if (!bstSheet) {
        bstSheet = ss.insertSheet(targetSheetName);
      }

      // Clean existing contents for fresh template restoration
      bstSheet.clearContents();

      // Row 1: Primary Column Headers
      var r1 = payload.headers_row1;
      if (r1 && r1.length > 0) {
        bstSheet.getRange(1, 1, 1, r1.length).setValues([r1]);
        var r1Range = bstSheet.getRange(1, 1, 1, r1.length);
        r1Range.setFontWeight("bold");
        r1Range.setBackground("#0F172A");
        r1Range.setFontColor("#FFFFFF");
        r1Range.setHorizontalAlignment("center");
      }

      // Row 2: Secondary / Sub-Headers
      var r2 = payload.headers_row2;
      if (r2 && r2.length > 0) {
        bstSheet.getRange(2, 1, 1, r2.length).setValues([r2]);
        var r2Range = bstSheet.getRange(2, 1, 1, r2.length);
        r2Range.setFontWeight("bold");
        r2Range.setBackground("#1E293B");
        r2Range.setFontColor("#94A3B8");
        r2Range.setHorizontalAlignment("center");
      }

      // Row 3+: Scripts, Trading Formulas, and Base Values
      var rows = payload.rows;
      if (rows && rows.length > 0) {
        var numRows = rows.length;
        var numCols = rows[0].length;
        // setValues automatically evaluates formulas starting with '='
        bstSheet.getRange(3, 1, numRows, numCols).setValues(rows);
      }

      return ContentService.createTextOutput(JSON.stringify({
        status: "success",
        mode: "init_bst",
        sheet: targetSheetName,
        rows_restored: rows ? rows.length : 0,
        message: "BST trading sheet headers, scripts, and formulas successfully restored!"
      })).setMimeType(ContentService.MimeType.JSON);
    }

    var sheet = ss.getSheetByName(targetSheetName);
    if (!sheet) {
      sheet = ss.insertSheet(targetSheetName);
    }

    // ========================================================================
    // MODE 2: BST Custom Trading Sheet In-Place Updates (Zero Formula Damage)
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
    // MODE 3: Standard Live Watchlist Table Mode (Non-BST Sheets ONLY)
    // ========================================================================
    // BST protection guard: NEVER wipe a sheet named BST with standard tabular watchlist!
    if (targetSheetName.toUpperCase() === "BST") {
      targetSheetName = "LiveMarket";
      sheet = ss.getSheetByName(targetSheetName);
      if (!sheet) {
        sheet = ss.insertSheet(targetSheetName);
      }
    }

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
      sheet: targetSheetName,
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
    message: "BSA Trading Bridge Live Market Data Webhook is active and listening for POST requests!"
  })).setMimeType(ContentService.MimeType.JSON);
}
