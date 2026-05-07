// ============================================================
//  DELETE /api/records/:id → 指定 id のレコードを削除
// ============================================================

const { kv } = require('@vercel/kv');

const KV_KEY = 'patrol_records';

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

    const records = (await kv.get(KV_KEY)) || [];
    const filtered = records.filter(function(r) {
      return String(r.id) !== String(id);
    });

    await kv.set(KV_KEY, filtered);

    console.log('[API] DELETE id=' + id);
    return res.status(200).json({ ok: true });

  } catch (err) {
    console.error('[API /records/:id] エラー:', err.message || err);
    return res.status(503).json({ ok: false, error: 'ストレージエラー' });
  }
};
