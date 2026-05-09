// ============================================================
//  GET /api/health → KV 接続確認
// ============================================================

const { kv } = require('@vercel/kv');

module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin',  '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Cache-Control', 'no-store');

  if (req.method === 'OPTIONS') return res.status(204).end();

  try {
    await kv.get('__health__');
    return res.status(200).json({ ok: true, ts: Date.now() });
  } catch (err) {
    const isKvMissing = err.message && err.message.includes('KV_');
    return res.status(503).json({
      ok:    false,
      error: isKvMissing
        ? 'Vercel KV が未接続です。Vercel ダッシュボードで Storage → KV を接続してください。'
        : ('KV エラー: ' + (err.message || 'unknown'))
    });
  }
};
