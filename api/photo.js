// GET  /api/photo?groupId=xxx&id=xxx&idx=N  → get one photo
// POST /api/photo?groupId=xxx&id=xxx&idx=N  → save one photo
//
// KV key: patrol:{groupId}:p:{id}:{idx}  → {dataUrl, name, takenAt}

const { kv } = require('@vercel/kv');

function photoKey(gid, id, idx) { return 'patrol:' + gid + ':p:' + id + ':' + idx; }

module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(204).end();

  const groupId = (req.query.groupId || 'default').replace(/[^a-zA-Z0-9\-_]/g, '').slice(0, 64) || 'default';
  const { id, idx } = req.query;
  if (!id || idx === undefined) return res.status(400).json({ ok: false, error: 'id and idx required' });

  try {
    if (req.method === 'GET') {
      const photo = await kv.get(photoKey(groupId, id, idx));
      if (!photo) return res.status(404).json({ ok: false, error: 'not found' });
      return res.status(200).json(photo);
    }

    if (req.method === 'POST') {
      const photo = req.body;
      if (!photo || !photo.dataUrl) return res.status(400).json({ ok: false, error: 'dataUrl required' });

      const bytes = Buffer.byteLength(photo.dataUrl, 'utf8');
      if (bytes > 2 * 1024 * 1024) return res.status(413).json({ ok: false, error: '写真が2MB超' });

      await kv.set(photoKey(groupId, id, idx), { dataUrl: photo.dataUrl, name: photo.name || '', takenAt: photo.takenAt || '' });
      return res.status(200).json({ ok: true });
    }

    return res.status(405).json({ error: 'Method not allowed' });
  } catch (err) {
    console.error('[photo] error:', err.message);
    return res.status(503).json({ ok: false, error: err.message || 'server error' });
  }
};
