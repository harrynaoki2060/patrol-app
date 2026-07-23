// DELETE /api/records/{id}?groupId=xxx → delete record and all its photos

const { kv } = require('@vercel/kv');

function indexKey(gid) { return 'patrol:' + gid + ':index'; }
function recKey(gid, id) { return 'patrol:' + gid + ':r:' + id; }
function photoKey(gid, id, idx) { return 'patrol:' + gid + ':p:' + id + ':' + idx; }

module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'DELETE') return res.status(405).json({ error: 'Method not allowed' });

  try {
    const { id } = req.query;
    const groupId = (req.query.groupId || 'default').replace(/[^a-zA-Z0-9\-_]/g, '').slice(0, 64) || 'default';
    if (!id) return res.status(400).json({ ok: false, error: 'id required' });

    const numId = Number(id);
    const ids = (await kv.get(indexKey(groupId))) || [];
    await kv.set(indexKey(groupId), ids.filter(i => i !== numId));
    await kv.del(recKey(groupId, numId));

    // Delete all photos (0-8)
    for (let i = 0; i < 9; i++) {
      await kv.del(photoKey(groupId, numId, i));
    }

    console.log('[records/:id] DELETE groupId=' + groupId + ' id=' + numId);
    return res.status(200).json({ ok: true });
  } catch (err) {
    console.error('[records/:id] error:', err.message);
    return res.status(503).json({ ok: false, error: err.message || 'server error' });
  }
};
