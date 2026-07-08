// ============================================================
// Clearance Removal Notifications — Google Apps Script
// ============================================================
// SETUP:
//   1. Open the bound script: Extensions → Apps Script (from the Sheet)
//      OR go to script.google.com and create a standalone project.
//   2. Paste this file as Code.gs
//   3. Create a second file called "Clearance Removal Notifications.html"
//      and paste that content.
//   4. Deploy → New deployment → Web app
//      - Execute as: Me
//      - Who has access: Anyone within [your org]  (or Anyone)
//   5. Share the Web App URL with your team.
//
// DATA SOURCE:
//   Update SHEET_ID and TAB_NAME below if you move the spreadsheet.
//
// MV STREAMS:
//   Stream data is populated by a Claude Code scheduled task that
//   calls the Vedder MCP gateway daily and writes results to the
//   "MV Streams" tab. No BigQuery access is needed.
// ============================================================

const SHEET_ID       = '1maI0JLyNGYxGvKugEsd97VLzcdf5txbCQoW23gcFBQ0';
const TAB_NAME       = 'Sheet1';
const MV_STREAMS_TAB = 'MV Streams';

// ── Web App entry point ──────────────────────────────────────
function doGet() {
  const template = HtmlService.createTemplateFromFile('Clearance Removal Notifications');
  template.sheetData     = getSheetData();
  template.lastUpdated   = Utilities.formatDate(
    new Date(), Session.getScriptTimeZone(), "MMM d, yyyy 'at' h:mm a z"
  );
  template.sheetUrl = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/edit?gid=788301353#gid=788301353`;

  return template.evaluate()
    .setTitle('Priority Content Removal Dashboard')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1.0');
}

// ── Priority tiers ──────────────────────────────────────────
function getPriority_(globalStreams) {
  if (globalStreams >= 100000) return 'Critical';
  if (globalStreams >= 10000)  return 'High';
  if (globalStreams >= 1000)   return 'Medium';
  return 'Low';
}

// ── MV Streams tab reader ───────────────────────────────────
function getMvStreamData_() {
  const ss    = SpreadsheetApp.openById(SHEET_ID);
  const sheet = ss.getSheetByName(MV_STREAMS_TAB);

  const streamMap = {};
  if (!sheet) return streamMap;

  const values = sheet.getDataRange().getValues();
  if (values.length < 2) return streamMap;

  values.slice(1).forEach(row => {
    const uri          = String(row[0] || '').trim();
    const globalStreams = parseInt(row[1], 10) || 0;
    if (uri) {
      streamMap[uri] = { globalStreams };
    }
  });

  return streamMap;
}

// ── Sheet reader ─────────────────────────────────────────────
function getSheetData() {
  const ss    = SpreadsheetApp.openById(SHEET_ID);
  const sheet = ss.getSheetByName(TAB_NAME);

  if (!sheet) {
    throw new Error(`Tab "${TAB_NAME}" not found in spreadsheet ${SHEET_ID}.`);
  }

  const values = sheet.getDataRange().getValues();
  if (values.length < 2) return JSON.stringify({ rows: [], mvDataAvailable: false });

  const rows = values.slice(1).map(row => {
    const uri     = String(row[0] || '').trim();
    const trackId = uri.startsWith('spotify:track:') ? uri.replace('spotify:track:', '') : uri;
    let   dateVal = row[5];

    let dateStr = '';
    if (dateVal instanceof Date) {
      dateStr = Utilities.formatDate(dateVal, Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm');
    } else {
      dateStr = String(dateVal || '').trim();
    }

    let dateAddedVal = row[7];
    let dateAddedStr = '';
    if (dateAddedVal instanceof Date) {
      dateAddedStr = Utilities.formatDate(dateAddedVal, Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm');
    } else {
      dateAddedStr = String(dateAddedVal || '').trim();
    }

    return {
      uri,
      trackId,
      title:                      String(row[1] || '').trim(),
      artists:                    String(row[2] || '').trim(),
      label:                      String(row[3] || '').trim(),
      licensor:                   String(row[4] || '').trim(),
      earliestLiveDate:           dateStr,
      publishersLackingClearance: String(row[6] || '').trim(),
      dateAdded:                  dateAddedStr,
    };
  }).filter(r => r.uri !== '');

  // ── Enrich with MV stream data from the "MV Streams" tab ──
  let mvData = {};
  let mvDataAvailable = false;
  try {
    mvData = getMvStreamData_();
    mvDataAvailable = Object.keys(mvData).length > 0;
  } catch (e) {
    Logger.log('MV Streams tab read failed: ' + e.message);
  }

  rows.forEach(row => {
    const mv = mvData[row.uri] || {};
    row.globalStreams = mv.globalStreams != null ? mv.globalStreams : 0;
    row.priority      = getPriority_(row.globalStreams);
  });

  return JSON.stringify({ rows, mvDataAvailable });
}

// ── Optional: onChange installable trigger ───────────────────
function installOnChangeTrigger() {
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === 'onSheetChange')
    .forEach(t => ScriptApp.deleteTrigger(t));

  ScriptApp.newTrigger('onSheetChange')
    .forSpreadsheet(SHEET_ID)
    .onChange()
    .create();

  Logger.log('onChange trigger installed successfully.');
}

function onSheetChange(e) {
  if (e.changeType !== 'INSERT_ROW') return;

  const sheet    = SpreadsheetApp.openById(SHEET_ID).getSheetByName(TAB_NAME);
  const rowCount = sheet.getLastRow() - 1;

  Logger.log(`New rows added to "${TAB_NAME}". Total rows: ${rowCount}`);
}
