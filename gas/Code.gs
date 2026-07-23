// Google Apps Script Web App
// 安全パトロールアプリ - 同期バックエンド
// APIs used: SpreadsheetApp, DriveApp, PropertiesService, ContentService, Utilities

var SHEET_RECORDS = 'Records';
var SHEET_LOG     = 'SyncLog';
var FOLDER_ROOT   = '安全パトロール'; // 安全パトロール
var COL_COUNT     = 17;

// ------------------------------------
// Routing
// ------------------------------------

function doGet(e) {
  try {
    if (!checkKey(e)) {
      return jsonOut({ error: 'Forbidden', code: 403 });
    }
    var action = getParam(e, 'action');
    if (action === 'health')  return onHealth();
    if (action === 'records') return onGetRecords(e);
    if (action === 'record')  return onGetRecord(e);
    if (action === 'photo')   return onGetPhoto(e);
    return jsonOut({ error: 'Unknown action: ' + action, code: 400 });
  } catch (err) {
    return jsonOut({ error: String(err), code: 500 });
  }
}

function doPost(e) {
  try {
    if (!checkKey(e)) {
      return jsonOut({ error: 'Forbidden', code: 403 });
    }
    var body   = JSON.parse(e.postData.contents);
    var action = body.action || '';
    if (action === 'upsert') return onUpsert(body);
    if (action === 'delete') return onDelete(body);
    if (action === 'photo')  return onSavePhoto(body);
    if (action === 'log')    return onLog(body);
    return jsonOut({ error: 'Unknown action: ' + action, code: 400 });
  } catch (err) {
    return jsonOut({ error: String(err), code: 500 });
  }
}

// ------------------------------------
// Auth
// ------------------------------------

function checkKey(e) {
  var stored = PropertiesService.getScriptProperties().getProperty('API_KEY');
  if (!stored) return true; // no key set = open (initial setup)
  var key = getParam(e, 'key') || '';
  return key === stored;
}

// ------------------------------------
// Health check
// ------------------------------------

function onHealth() {
  var props = PropertiesService.getScriptProperties();
  var ssId  = props.getProperty('SPREADSHEET_ID');
  return jsonOut({
    ok: true,
    spreadsheetId: ssId || 'not set',
    timestamp: jstNow()
  });
}

// ------------------------------------
// GET records
// ------------------------------------

function onGetRecords(e) {
  var updatedSince = getParam(e, 'updatedSince') || '';
  var sheet  = getSheet(SHEET_RECORDS);
  var data   = sheet.getDataRange().getValues();
  if (data.length <= 1) {
    return jsonOut({ records: [], count: 0 });
  }
  var records = [];
  for (var i = 1; i < data.length; i++) {
    var row = data[i];
    if (!row[0]) continue;
    var rec = rowToRecord(row);
    if (updatedSince && rec.updatedAt <= updatedSince) continue;
    records.push(rec);
  }
  return jsonOut({ records: records, count: records.length });
}

function onGetRecord(e) {
  var id = getParam(e, 'id');
  if (!id) return jsonOut({ error: 'id is required', code: 400 });
  var sheet = getSheet(SHEET_RECORDS);
  var row   = findRow(sheet, Number(id));
  if (!row) return jsonOut({ error: 'Record not found', code: 404 });
  return jsonOut({ record: rowToRecord(row) });
}

// ------------------------------------
// POST upsert
// ------------------------------------

function onUpsert(body) {
  var record = body.record;
  if (!record || !record.id) {
    return jsonOut({ error: 'record.id is required', code: 400 });
  }
  var sheet  = getSheet(SHEET_RECORDS);
  var rowNum = findRowNum(sheet, Number(record.id));
  var now    = jstNow();
  var rowData = recordToRow(record, now);
  if (rowNum) {
    sheet.getRange(rowNum, 1, 1, COL_COUNT).setValues([rowData]);
  } else {
    var last = sheet.getLastRow();
    sheet.getRange(last + 1, 1, 1, COL_COUNT).setValues([rowData]);
  }
  return jsonOut({ id: record.id, updatedAt: now });
}

// ------------------------------------
// POST delete (logical)
// ------------------------------------

function onDelete(body) {
  var id = body.id;
  if (!id) return jsonOut({ error: 'id is required', code: 400 });
  var sheet  = getSheet(SHEET_RECORDS);
  var rowNum = findRowNum(sheet, Number(id));
  if (!rowNum) return jsonOut({ error: 'Record not found', code: 404 });
  var now = jstNow();
  sheet.getRange(rowNum, 16).setValue(now);   // updatedAt (col P)
  sheet.getRange(rowNum, 17).setValue(true);  // deleted   (col Q)
  return jsonOut({ id: id, deletedAt: now });
}

// ------------------------------------
// POST photo (Drive upload)
// ------------------------------------

function onSavePhoto(body) {
  if (!body.recordId)  return jsonOut({ error: 'recordId required', code: 400 });
  if (!body.base64)    return jsonOut({ error: 'base64 required',   code: 400 });
  if (!body.name)      return jsonOut({ error: 'name required',     code: 400 });
  if (!body.mimeType)  return jsonOut({ error: 'mimeType required', code: 400 });
  if (!body.yearMonth) return jsonOut({ error: 'yearMonth required',code: 400 });

  var b64     = body.base64.replace(/^data:[^,]+,/, '');
  var decoded = Utilities.base64Decode(b64);
  var blob    = Utilities.newBlob(decoded, body.mimeType, body.name);
  var folder  = getOrCreateFolder(body.yearMonth);
  var file    = folder.createFile(blob);

  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);

  var fileId = file.getId();
  var url    = 'https://drive.google.com/uc?export=view&id=' + fileId;
  return jsonOut({ fileId: fileId, url: url, name: body.name });
}

function onGetPhoto(e) {
  var fileId = getParam(e, 'fileId');
  if (!fileId) return jsonOut({ error: 'fileId required', code: 400 });
  var file = DriveApp.getFileById(fileId);
  var url  = 'https://drive.google.com/uc?export=view&id=' + fileId;
  return jsonOut({ fileId: fileId, url: url, name: file.getName() });
}

// ------------------------------------
// POST log
// ------------------------------------

function onLog(body) {
  var sheet = getLogSheet();
  var last  = sheet.getLastRow();
  sheet.getRange(last + 1, 1, 1, 6).setValues([[
    jstNow(),
    body.ua       || '',
    body.sent     || 0,
    body.received || 0,
    body.photos   || 0,
    body.errorMsg || ''
  ]]);
  return jsonOut({ logged: true });
}

// ------------------------------------
// Spreadsheet helpers
// ------------------------------------

function getSS() {
  var props = PropertiesService.getScriptProperties();
  var ssId  = props.getProperty('SPREADSHEET_ID');
  if (ssId) {
    return SpreadsheetApp.openById(ssId);
  }
  // Fallback: bound script (created from inside a spreadsheet)
  return SpreadsheetApp.getActiveSpreadsheet();
}

function getSheet(name) {
  var ss    = getSS();
  var sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
    if (name === SHEET_RECORDS) initHeader(sheet);
  }
  return sheet;
}

function getLogSheet() {
  var ss    = getSS();
  var sheet = ss.getSheetByName(SHEET_LOG);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_LOG);
    sheet.getRange(1, 1, 1, 6).setValues([[
      'timestamp', 'ua', 'sent', 'received', 'photos', 'error'
    ]]);
    sheet.getRange(1, 1, 1, 6).setFontWeight('bold');
  }
  return sheet;
}

function initHeader(sheet) {
  var h = [
    'id', 'date', 'projectName', 'termStart', 'termEnd',
    'contractor', 'subcontractor', 'inspector', 'progressRate',
    'notes1', 'notes2', 'notes3', 'checks',
    'photoCount', 'photoMeta', 'updatedAt', 'deleted'
  ];
  sheet.getRange(1, 1, 1, COL_COUNT).setValues([h]);
  sheet.getRange(1, 1, 1, COL_COUNT).setFontWeight('bold');
  sheet.setFrozenRows(1);
}

function findRow(sheet, id) {
  var data = sheet.getDataRange().getValues();
  for (var i = 1; i < data.length; i++) {
    if (Number(data[i][0]) === id) return data[i];
  }
  return null;
}

function findRowNum(sheet, id) {
  var data = sheet.getDataRange().getValues();
  for (var i = 1; i < data.length; i++) {
    if (Number(data[i][0]) === id) return i + 1;
  }
  return null;
}

function rowToRecord(row) {
  return {
    id:            Number(row[0]),
    date:          String(row[1]  || ''),
    projectName:   String(row[2]  || ''),
    termStart:     String(row[3]  || ''),
    termEnd:       String(row[4]  || ''),
    contractor:    String(row[5]  || ''),
    subcontractor: String(row[6]  || ''),
    inspector:     String(row[7]  || ''),
    progressRate:  Number(row[8]  || 0),
    notes1:        String(row[9]  || ''),
    notes2:        String(row[10] || ''),
    notes3:        String(row[11] || ''),
    checks:        safeJson(row[12], {}),
    photoCount:    Number(row[13] || 0),
    photoMeta:     safeJson(row[14], []),
    updatedAt:     String(row[15] || ''),
    deleted:       row[16] === true || String(row[16]) === 'TRUE'
  };
}

function recordToRow(record, now) {
  return [
    Number(record.id),
    record.date          || '',
    record.projectName   || '',
    record.termStart     || '',
    record.termEnd       || '',
    record.contractor    || '',
    record.subcontractor || '',
    record.inspector     || '',
    Number(record.progressRate || 0),
    record.notes1        || '',
    record.notes2        || '',
    record.notes3        || '',
    JSON.stringify(record.checks    || {}),
    Number(record.photoCount || 0),
    JSON.stringify(record.photoMeta || []),
    now,
    record.deleted === true
  ];
}

// ------------------------------------
// Drive helpers
// ------------------------------------

function getOrCreateFolder(yearMonth) {
  // yearMonth = 'YYYY/MM'
  var parts = yearMonth.split('/');
  var year  = parts[0];
  var month = parts[1];

  var rootIt = DriveApp.getFoldersByName(FOLDER_ROOT);
  var root   = rootIt.hasNext() ? rootIt.next() : DriveApp.createFolder(FOLDER_ROOT);

  var yearIt = root.getFoldersByName(year);
  var yearF  = yearIt.hasNext() ? yearIt.next() : root.createFolder(year);

  var monIt  = yearF.getFoldersByName(month);
  return monIt.hasNext() ? monIt.next() : yearF.createFolder(month);
}

// ------------------------------------
// Utility helpers
// ------------------------------------

function getParam(e, key) {
  return (e && e.parameter && e.parameter[key]) ? e.parameter[key] : '';
}

function jstNow() {
  var d   = new Date();
  var jst = new Date(d.getTime() + 9 * 60 * 60 * 1000);
  var pad = function(n) { return n < 10 ? '0' + n : '' + n; };
  return jst.getUTCFullYear() + '-'
    + pad(jst.getUTCMonth() + 1) + '-'
    + pad(jst.getUTCDate())      + ' '
    + pad(jst.getUTCHours())     + ':'
    + pad(jst.getUTCMinutes())   + ':'
    + pad(jst.getUTCSeconds());
}

function safeJson(val, fallback) {
  if (!val || val === '') return fallback;
  try { return JSON.parse(val); } catch (e) { return fallback; }
}

function jsonOut(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

// ------------------------------------
// One-time setup (run manually from editor)
// ------------------------------------

// Step 1: Run this FIRST to register the spreadsheet ID.
// Replace the ID below with your actual spreadsheet ID from the URL.
// URL format: https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit
function setupSpreadsheet() {
  var ssId = 'YOUR_SPREADSHEET_ID_HERE'; // <-- replace this
  PropertiesService.getScriptProperties().setProperty('SPREADSHEET_ID', ssId);
  Logger.log('SPREADSHEET_ID saved: ' + ssId);
}

// Step 2: Run this to register the API key.
function setupApiKey() {
  var key = 'patrol-2026-change-me'; // <-- replace with your own key
  PropertiesService.getScriptProperties().setProperty('API_KEY', key);
  Logger.log('API_KEY saved: ' + key);
}

// Step 3: Run this to verify setup is correct.
function testHealth() {
  var result = onHealth();
  Logger.log(result.getContent());
}
