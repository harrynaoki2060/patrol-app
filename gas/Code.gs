// ============================================================
// 安全パトロールアプリ — Google Apps Script Web App
// ============================================================
// デプロイ設定:
//   実行者: 自分（スクリプトオーナー）
//   アクセス: 全員
// ============================================================

// ── 定数 ────────────────────────────────────────────────────
var SHEET_NAME   = 'Records';
var LOG_SHEET    = 'SyncLog';
var FOLDER_ROOT  = '安全パトロール';
var COL_COUNT    = 17;

// ── ルーティング ─────────────────────────────────────────────

function doGet(e) {
  try {
    if (!checkApiKey(e)) return forbidden();
    var action = (e.parameter && e.parameter.action) || '';
    switch (action) {
      case 'health':  return handleHealth();
      case 'records': return handleGetRecords(e);
      case 'record':  return handleGetRecord(e);
      case 'photo':   return handleGetPhoto(e);
      default:        return error('Unknown action: ' + action, 400);
    }
  } catch (ex) {
    return error(ex.message || String(ex), 500);
  }
}

function doPost(e) {
  try {
    if (!checkApiKey(e)) return forbidden();
    var body   = JSON.parse(e.postData.contents);
    var action = body.action || '';
    switch (action) {
      case 'upsert': return handleUpsert(body);
      case 'delete': return handleDelete(body);
      case 'photo':  return handleSavePhoto(body);
      case 'log':    return handleLog(body);
      default:       return error('Unknown action: ' + action, 400);
    }
  } catch (ex) {
    return error(ex.message || String(ex), 500);
  }
}

// ── 認証 ──────────────────────────────────────────────────────

function checkApiKey(e) {
  // GAS は任意ヘッダーを受け取れないため、クエリパラメーターで受け渡す
  var key = (e.parameter && e.parameter.key) || '';
  var stored = PropertiesService.getScriptProperties().getProperty('API_KEY');
  if (!stored) return true;  // API_KEY 未設定の場合は認証スキップ（初回セットアップ用）
  return key === stored;
}

// ── ヘルスチェック ────────────────────────────────────────────

function handleHealth() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  return ok({
    ok: true,
    spreadsheetId: ss.getId(),
    spreadsheetName: ss.getName(),
    timestamp: jstNow()
  });
}

// ── レコード取得（GET） ───────────────────────────────────────

function handleGetRecords(e) {
  var updatedSince = (e.parameter && e.parameter.updatedSince) || '';
  var sheet = getOrCreateSheet(SHEET_NAME);
  var rows  = sheet.getDataRange().getValues();

  // 1行目はヘッダー
  if (rows.length <= 1) return ok({ records: [], count: 0 });

  var records = [];
  for (var i = 1; i < rows.length; i++) {
    var row = rows[i];
    if (!row[0]) continue;  // id が空の行はスキップ
    var rec = rowToRecord(row);

    // updatedSince フィルター（ISO文字列で比較）
    if (updatedSince && rec.updatedAt <= updatedSince) continue;

    records.push(rec);
  }

  return ok({ records: records, count: records.length });
}

function handleGetRecord(e) {
  var id    = e.parameter && e.parameter.id;
  if (!id) return error('id is required', 400);
  var sheet = getOrCreateSheet(SHEET_NAME);
  var row   = findRowById(sheet, Number(id));
  if (!row) return error('Record not found', 404);
  return ok({ record: rowToRecord(row) });
}

// ── レコード保存（POST upsert） ───────────────────────────────

function handleUpsert(body) {
  var record = body.record;
  if (!record || !record.id) return error('record.id is required', 400);

  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    var sheet  = getOrCreateSheet(SHEET_NAME);
    var rowNum = findRowNumById(sheet, Number(record.id));
    var now    = jstNow();
    var rowData = recordToRow(record, now);

    if (rowNum) {
      // 既存行を上書き
      sheet.getRange(rowNum, 1, 1, COL_COUNT).setValues([rowData]);
    } else {
      // 末尾に追加
      var lastRow = sheet.getLastRow();
      if (lastRow === 0) {
        // シートが空の場合はヘッダーを書き込む
        writeHeader(sheet);
        sheet.getRange(2, 1, 1, COL_COUNT).setValues([rowData]);
      } else {
        sheet.getRange(lastRow + 1, 1, 1, COL_COUNT).setValues([rowData]);
      }
    }
    return ok({ id: record.id, updatedAt: now });
  } finally {
    lock.releaseLock();
  }
}

// ── レコード論理削除（POST delete） ──────────────────────────

function handleDelete(body) {
  var id = body.id;
  if (!id) return error('id is required', 400);

  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    var sheet  = getOrCreateSheet(SHEET_NAME);
    var rowNum = findRowNumById(sheet, Number(id));
    if (!rowNum) return error('Record not found', 404);

    var now = jstNow();
    // deleted = TRUE, updatedAt 更新のみ（P列=16, Q列=17）
    sheet.getRange(rowNum, 16).setValue(now);   // updatedAt
    sheet.getRange(rowNum, 17).setValue(true);  // deleted
    return ok({ id: id, deletedAt: now });
  } finally {
    lock.releaseLock();
  }
}

// ── 写真保存（POST photo） ────────────────────────────────────

function handleSavePhoto(body) {
  var required = ['recordId', 'base64', 'name', 'mimeType', 'yearMonth'];
  for (var i = 0; i < required.length; i++) {
    if (!body[required[i]]) return error(required[i] + ' is required', 400);
  }

  var folder   = getOrCreateFolder(body.yearMonth);
  var decoded  = Utilities.base64Decode(body.base64.replace(/^data:[^,]+,/, ''));
  var blob     = Utilities.newBlob(decoded, body.mimeType, body.name);
  var file     = folder.createFile(blob);

  // 閲覧共有を「リンクを知っている全員」に設定
  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);

  var fileId = file.getId();
  var url    = 'https://drive.google.com/uc?export=view&id=' + fileId;

  return ok({ fileId: fileId, url: url, name: body.name });
}

function handleGetPhoto(e) {
  var fileId = e.parameter && e.parameter.fileId;
  if (!fileId) return error('fileId is required', 400);
  var file = DriveApp.getFileById(fileId);
  var url  = 'https://drive.google.com/uc?export=view&id=' + fileId;
  return ok({ fileId: fileId, url: url, name: file.getName() });
}

// ── 同期ログ（POST log） ──────────────────────────────────────

function handleLog(body) {
  var sheet   = getOrCreateSheet(LOG_SHEET);
  var lastRow = sheet.getLastRow();
  if (lastRow === 0) {
    sheet.getRange(1, 1, 1, 6).setValues([[
      '同期日時', '端末UA', '送信件数', '取得件数', '写真枚数', 'エラー'
    ]]);
    lastRow = 1;
  }
  sheet.getRange(lastRow + 1, 1, 1, 6).setValues([[
    jstNow(),
    body.ua         || '',
    body.sent       || 0,
    body.received   || 0,
    body.photos     || 0,
    body.errorMsg   || ''
  ]]);
  return ok({ logged: true });
}

// ── ヘルパー: Spreadsheet ─────────────────────────────────────

function getOrCreateSheet(name) {
  var ss    = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
    if (name === SHEET_NAME) writeHeader(sheet);
  }
  return sheet;
}

function writeHeader(sheet) {
  var headers = [
    'id','date','projectName','termStart','termEnd',
    'contractor','subcontractor','inspector','progressRate',
    'notes1','notes2','notes3','checks',
    'photoCount','photoMeta','updatedAt','deleted'
  ];
  sheet.getRange(1, 1, 1, COL_COUNT).setValues([headers]);
  sheet.getRange(1, 1, 1, COL_COUNT).setFontWeight('bold');
  sheet.setFrozenRows(1);
}

function findRowById(sheet, id) {
  var rows = sheet.getDataRange().getValues();
  for (var i = 1; i < rows.length; i++) {
    if (Number(rows[i][0]) === id) return rows[i];
  }
  return null;
}

function findRowNumById(sheet, id) {
  var rows = sheet.getDataRange().getValues();
  for (var i = 1; i < rows.length; i++) {
    if (Number(rows[i][0]) === id) return i + 1;  // 1-indexed
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
    checks:        safeParseJson(row[12], {}),
    photoCount:    Number(row[13] || 0),
    photoMeta:     safeParseJson(row[14], []),
    updatedAt:     String(row[15] || ''),
    deleted:       row[16] === true || row[16] === 'TRUE'
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

// ── ヘルパー: Drive ───────────────────────────────────────────

function getOrCreateFolder(yearMonth) {
  // yearMonth: 'YYYY/MM'
  var parts  = yearMonth.split('/');
  var year   = parts[0];
  var month  = parts[1];

  // ルートフォルダ
  var roots  = DriveApp.getFoldersByName(FOLDER_ROOT);
  var root   = roots.hasNext() ? roots.next() : DriveApp.createFolder(FOLDER_ROOT);

  // 年フォルダ
  var years  = root.getFoldersByName(year);
  var yearF  = years.hasNext() ? years.next() : root.createFolder(year);

  // 月フォルダ
  var months = yearF.getFoldersByName(month);
  return months.hasNext() ? months.next() : yearF.createFolder(month);
}

// ── ヘルパー: 共通 ────────────────────────────────────────────

function jstNow() {
  var d   = new Date();
  var jst = new Date(d.getTime() + 9 * 60 * 60 * 1000);
  var pad = function(n) { return n < 10 ? '0' + n : String(n); };
  return jst.getUTCFullYear() + '-' +
    pad(jst.getUTCMonth() + 1) + '-' +
    pad(jst.getUTCDate())      + ' ' +
    pad(jst.getUTCHours())     + ':' +
    pad(jst.getUTCMinutes())   + ':' +
    pad(jst.getUTCSeconds());
}

function safeParseJson(val, fallback) {
  if (!val || val === '') return fallback;
  try { return JSON.parse(val); } catch (e) { return fallback; }
}

function ok(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

function error(msg, code) {
  return ContentService
    .createTextOutput(JSON.stringify({ error: msg, code: code || 500 }))
    .setMimeType(ContentService.MimeType.JSON);
}

function forbidden() {
  return ContentService
    .createTextOutput(JSON.stringify({ error: 'Forbidden: invalid API key', code: 403 }))
    .setMimeType(ContentService.MimeType.JSON);
}

// ── 初回セットアップ用（手動実行） ────────────────────────────
// スクリプトエディタから一度だけ実行して API キーを登録する

function setupApiKey() {
  var key = 'patrol-2026-change-me';  // ← ここを自分のキーに書き換えてから実行
  PropertiesService.getScriptProperties().setProperty('API_KEY', key);
  Logger.log('API_KEY を登録しました: ' + key);
}
