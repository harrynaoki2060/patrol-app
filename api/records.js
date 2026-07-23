// GET  /api/records?groupId=xxx   → all text-only records for group
// POST /api/records?groupId=xxx   → upsert one text-only record (photos stripped server-side)
//
// KV structure:
//   patrol:{groupId}:index  → number[]
//   patrol:{groupId}:r:{id} → Record (photos:[], photoCount:N)

const { kv } = require('@vercel/kv');

function indexKey(gid) { return 'patrol:' + gid + ':index'; }
function recKey(gid, id) { return 'patrol:' + gid + ':r:' + id; }

module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(204).end();

  const groupId = (req.query.groupId || 'default').replace(/[^a-zA-Z0-9\-_]/g, '').slice(0, 64) || 'default';

  try {
    if (req.method === 'GET') {
      const ids = (await kv.get(indexKey(groupId))) || [];
      if (!ids.length) return res.status(200).json([]);
      const recent = ids.slice(-200);
      const keys = recent.map(id => recKey(groupId, id));
      const vals = await kv.mget(...keys);
      const records = vals.filter(Boolean).sort((a, b) => b.id - a.id);
      return res.status(200).json(records);
    }

    if (req.method === 'POST') {
      const body = req.body;
      if (!body || !body.id) return res.status(400).json({ ok: false, error: 'id required' });

      const id = Number(body.id);
      // Strip photos — store text only
      const { photos, ...rest } = body;
      const textRecord = { ...rest, photos: [], photoCount: (photos || []).length, synced: true };

      const ids = (await kv.get(indexKey(groupId))) || [];
      if (!ids.includes(id)) {
        ids.push(id);
        await kv.set(indexKey(groupId), ids.sort((a, b) => a - b).slice(-200));
      }
      await kv.set(recKey(groupId, id), textRecord);

      console.log('[records] POST groupId=' + groupId + ' id=' + id);
      return res.status(200).json({ ok: true });
    }

    return res.status(405).json({ error: 'Method not allowed' });
  } catch (err) {
    console.error('[records] error:', err.message);
    return res.status(503).json({ ok: false, error: err.message || 'server error' });
  }
};
