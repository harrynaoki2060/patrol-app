// ============================================================
//  DELETE /api/records/:id → 指定 id のレコードを削除
//
//  KV 構造（records.js と同じ）:
//    patrol:index   → number[]  レコードIDの配列
//    patrol:r:{id}  → Record    個別レコード
// ============================================================

const { kv } = require('@vercel/kv');

const INDEX_KEY = 'patrol:index';
const recKey = function(id) { return 'patrol:r:' + id; };

module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin',  '*');
  res.setHeader('Access-Control-Allow-Methods', 'DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    return res.status(204).end();
  }

  if (req.method !== 'DELETE') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const { id } = req.query;

    if (!id) {
      return res.status(400).json({ ok: false, error: 'id が必要です' });
    }

    const numId = Number(id);

    // インデックスから削除
    const ids = (await kv.get(INDEX_KEY)) || [];
    const newIds = ids.filter(function(i) { return i !== numId; });
    await kv.set(INDEX_KEY, newIds);

    // 個別レコードキーを削除
    await kv.del(recKey(numId));

    console.log('[API] DELETE id=' + numId);
    return res.status(200).json({ ok: true });

  } catch (err) {
    console.error('[API /records/:id] エラー:', err.message || err);
    const isKvMissing = err.message && err.message.includes('KV_');
    return res.status(503).json({
      ok:    false,
      error: isKvMissing
        ? 'Vercel KV が未接続です。Vercel ダッシュボードで Storage → KV を接続してください。'
        : ('サーバーエラー: ' + (err.message || 'unknown'))
    });
  }
};
