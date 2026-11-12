/**
 * ==============================================================================
 * UPSTOX LIVE MARKET DATA GOOGLE APPS SCRIPT WEBHOOK (Zero GCP Setup)
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
    var rows = payload.data; // 2D array: [[Symbol, Instrument Key, LTP, Change, VWAP, Open, High, Low, Close, Volume, Updated At], ...]

    if (!rows || rows.length === 0) {
      return ContentService.createTextOutput(JSON.stringify({
        status: "ok",
        message: "Empty payload, nothing to update"
      })).setMimeType(ContentService.MimeType.JSON);
    }

    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName(targetSheetName);

    // If sheet doesn't exist yet, create it
    if (!sheet) {
      sheet = ss.insertSheet(targetSheetName);
    }

    var numRows = rows.length;
    var numCols = rows[0].length;

    // Clear old rows/duplicates completely
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
      // Prices: Cols 3 to 9 (LTP, Change, VWAP, Open, High, Low, Close) formatted as decimals
      sheet.getRange(2, 3, numRows - 1, 7).setNumberFormat("#,##0.00");
      // Volume: Col 10 formatted as integer
      sheet.getRange(2, 10, numRows - 1, 1).setNumberFormat("#,##0");
      // Text alignments
      sheet.getRange(2, 1, numRows - 1, 2).setHorizontalAlignment("left");
      sheet.getRange(2, 3, numRows - 1, 8).setHorizontalAlignment("right");
      sheet.getRange(2, 11, numRows - 1, 1).setHorizontalAlignment("center");
    }

    return ContentService.createTextOutput(JSON.stringify({
      status: "success",
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
