// ============================================================
//  GET  /api/records  → 全レコード返却
//  POST /api/records  → レコード保存（id重複時は上書き）
//
//  データストア: Vercel KV (Redis)
//  KV_KEY: 'patrol_records' → JSON配列
// ============================================================

const { kv } = require('@vercel/kv');

const KV_KEY = 'patrol_records';

module.exports = async function handler(req, res) {
  // CORS ヘッダー（同一ドメインでも安全のため設定）
  res.setHeader('Access-Control-Allow-Origin',  '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  // プリフライトリクエスト
  if (req.method === 'OPTIONS') {
    return res.status(204).end();
  }

  try {
    // ── GET: 全レコードを返す ─────────────────────────────
    if (req.method === 'GET') {
      const records = (await kv.get(KV_KEY)) || [];
      // 新しい順に並び替えて返す
      const sorted = Array.isArray(records)
        ? records.sort(function(a, b) { return b.id - a.id; })
        : [];
      return res.status(200).json(sorted);
    }

    // ── POST: レコード保存 ────────────────────────────────
    if (req.method === 'POST') {
      const record = req.body;

      if (!record || !record.id) {
        return res.status(400).json({ ok: false, error: 'id が必要です' });
      }

      const records = (await kv.get(KV_KEY)) || [];

      // 同じ id のレコードがあれば上書き、なければ追加
      const idx = records.findIndex(function(r) { return r.id === record.id; });
      if (idx >= 0) {
        records[idx] = record;
      } else {
        records.push(record);
      }

      await kv.set(KV_KEY, records);
      return res.status(200).json({ ok: true });
    }

    return res.status(405).json({ error: 'Method not allowed' });

  } catch (err) {
    console.error('[API /records] エラー:', err.message || err);
    // KV 未設定の場合は 503 を返す（アプリは IndexedDB で動作継続）
    return res.status(503).json({
      ok: false,
      error: 'ストレージが設定されていません。Vercel KV を接続してください。'
    });
  }
};
