// ============================================================
//  GET  /api/records  → 全レコード返却
//  POST /api/records  → レコード保存（upsert）
//
//  KV 構造:
//    patrol:index       → number[]  レコードIDの配列
//    patrol:r:{id}      → Record    個別レコード
//
//  ※ 1キーに全件詰め込まず個別保存することで
//    写真付きの大容量レコードも安全に扱える
// ============================================================

const { kv } = require('@vercel/kv');

const INDEX_KEY  = 'patrol:index';
const recKey = function(id) { return 'patrol:r:' + id; };

module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin',  '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(204).end();

  try {
    // ── GET: インデックス取得 → 全レコードを mget ──────────────
    if (req.method === 'GET') {
      const ids = (await kv.get(INDEX_KEY)) || [];
      if (!ids.length) return res.status(200).json([]);

      // 最大50件に絞る（古い順に切り捨て）
      const recent = ids.slice(-50);
      const keys   = recent.map(recKey);
      const vals   = await kv.mget(...keys);

      const records = vals
        .filter(Boolean)
        .sort(function(a, b) { return b.id - a.id; });

      return res.status(200).json(records);
    }

    // ── POST: 個別レコードを upsert ────────────────────────────
    if (req.method === 'POST') {
      const record = req.body;

      if (!record || !record.id) {
        return res.status(400).json({ ok: false, error: 'id が必要です' });
      }

      const id = Number(record.id);

      // インデックス更新
      const ids = (await kv.get(INDEX_KEY)) || [];
      if (!ids.includes(id)) {
        ids.push(id);
        // 古いIDを削除（最大100件保持）
        const trimmed = ids.sort(function(a, b) { return a - b; }).slice(-100);
        await kv.set(INDEX_KEY, trimmed);
      }

      // レコード個別保存（有効期限なし）
      await kv.set(recKey(id), record);

      console.log('[API] POST id=' + id);
      return res.status(200).json({ ok: true });
    }

    return res.status(405).json({ error: 'Method not allowed' });

  } catch (err) {
    console.error('[API /records] エラー:', err.message || err);
    const isKvMissing = err.message && err.message.includes('KV_');
    return res.status(503).json({
      ok:    false,
      error: isKvMissing
        ? 'Vercel KV が未接続です。Vercel ダッシュボードで Storage → KV を接続してください。'
        : ('サーバーエラー: ' + (err.message || 'unknown'))
    });
  }
};
