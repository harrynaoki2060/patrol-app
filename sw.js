// ============================================================
//  安全パトロール Service Worker  v12
//  対象: iPad Safari PWA 完全オフライン起動
//
//  ポイント:
//  1. install  → index.html を root('/')と '/index.html' 両キーでキャッシュ
//  2. activate → 'patrol-' プレフィックスの旧キャッシュを全削除
//               skipWaiting + clients.claim を確実に実行
//  3. fetch    → navigate は 3 段フォールバックで必ず何か返す
//  4. message  → 'SKIP_WAITING' で強制更新をサポート
// ============================================================

var CACHE_NAME   = 'patrol-v12';      // ← バージョンを上げるだけで旧キャッシュが消える
var CACHE_PREFIX = 'patrol-';        // このプレフィックスの旧キャッシュをすべて削除

// オフライン緊急フォールバック HTML（キャッシュが何もない最終手段）
var OFFLINE_PAGE =
  '<!DOCTYPE html><html lang="ja"><head>' +
  '<meta charset="UTF-8">' +
  '<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">' +
  '<meta name="apple-mobile-web-app-capable" content="yes">' +
  '<title>安全パトロール - オフライン</title>' +
  '<style>' +
  '*{box-sizing:border-box;margin:0;padding:0}' +
  'body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;' +
  'background:#1e40af;color:#fff;min-height:100vh;' +
  'display:flex;align-items:center;justify-content:center;' +
  'text-align:center;padding:32px;}' +
  '.card{background:rgba(255,255,255,.15);border-radius:16px;padding:32px 24px;}' +
  'h1{font-size:20px;font-weight:700;margin-bottom:10px;}' +
  'p{font-size:14px;line-height:1.8;opacity:.9;margin-bottom:6px;}' +
  '.sub{font-size:12px;opacity:.7;margin-top:14px;}' +
  '</style></head>' +
  '<body><div class="card">' +
  '<h1>&#128535;&nbsp;オフライン</h1>' +
  '<p>キャッシュが見つかりません。</p>' +
  '<p>オンライン状態で一度アプリを開き<br>再度ホーム画面から起動してください。</p>' +
  '<p class="sub">安全パトロール点検表</p>' +
  '</div></body></html>';

// ============================================================
// 1. Install: index.html を2キーでキャッシュ
// ============================================================
self.addEventListener('install', function(event) {
  console.log('[SW v12] ▶ install 開始');

  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(function(cache) {
        // ── コアファイル: index.html を root と /index.html 両キーに保存 ──
        return fetch('./index.html', { cache: 'reload' })
          .then(function(res) {
            if (!res || !res.ok) {
              throw new Error('index.html fetch failed: ' + (res ? res.status : 'no response'));
            }
            var c1 = res.clone();
            var c2 = res.clone();
            // '.'  → http://IP:8080/          (manifest start_url と一致)
            // './index.html' → http://IP:8080/index.html
            return Promise.all([
              cache.put('.',            c1),
              cache.put('./index.html', c2)
            ]);
          })
          .then(function() {
            console.log('[SW v12] ✓ index.html を 2 キーでキャッシュ完了');
          })
          // index.html のキャッシュ失敗は致命的だが install は続行する
          .catch(function(e) {
            console.error('[SW v12] ✗ index.html キャッシュ失敗:', e.message);
          })

          // ── その他ファイル（1つ失敗しても継続）──
          .then(function() {
            var extras = [
              './manifest.json',
              './icon-180.png',
              './icon-192.png',
              './icon-512.png',
              './xlsx.full.min.js',       // ローカル配置（CDN不要・オフライン確実）
              './apple-touch-icon.png',   // iOS が慣例パスで自動リクエスト
              './favicon.ico'             // ブラウザが自動リクエスト
            ];
            return Promise.all(
              extras.map(function(url) {
                return cache.add(url)
                  .then(function() { console.log('[SW v12] ✓ cached:', url); })
                  .catch(function(e) { console.warn('[SW v12] ✗ skip:', url, '-', e.message || e); });
              })
            );
          });
      })
      .then(function() {
        console.log('[SW v12] ▶ install 完了 → skipWaiting()');
        // 旧 SW をすぐ置き換える（waiting をスキップ）
        return self.skipWaiting();
      })
      .catch(function(e) {
        console.error('[SW v12] install エラー:', e);
        // エラーがあっても skipWaiting は必ず呼ぶ
        return self.skipWaiting();
      })
  );
});

// ============================================================
// 2. Activate: 旧キャッシュを全削除 → clients.claim()
// ============================================================
self.addEventListener('activate', function(event) {
  console.log('[SW v12] ▶ activate 開始');

  event.waitUntil(
    // 旧 patrol-v* キャッシュを全削除
    caches.keys()
      .then(function(keys) {
        var targets = keys.filter(function(k) {
          // 'patrol-' で始まり、かつ現バージョン以外をすべて削除
          return k.startsWith(CACHE_PREFIX) && k !== CACHE_NAME;
        });
        console.log('[SW v12] 削除対象キャッシュ:', targets);
        return Promise.all(
          targets.map(function(k) {
            return caches.delete(k)
              .then(function(ok) { console.log('[SW v12] ✓ 削除:', k, ok); })
              .catch(function(e) { console.warn('[SW v12] ✗ 削除失敗:', k, e); });
          })
        );
      })
      .then(function() {
        console.log('[SW v12] ▶ clients.claim()');
        // 開いているすべてのタブを即座に制御下に置く
        return self.clients.claim();
      })
      .then(function() {
        console.log('[SW v12] ✓ activate 完了 / キャッシュ名:', CACHE_NAME);
      })
      .catch(function(e) {
        console.error('[SW v12] activate エラー:', e);
        // エラーがあっても clients.claim は必ず呼ぶ
        return self.clients.claim().catch(function(){});
      })
  );
});

// ============================================================
// 3. Message: クライアントから skipWaiting を要求できる
// ============================================================
self.addEventListener('message', function(event) {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    console.log('[SW v12] message → SKIP_WAITING 受信 → skipWaiting()');
    self.skipWaiting();
  }
});

// ============================================================
// 4. Fetch: Cache First + 3段フォールバック
// ============================================================
self.addEventListener('fetch', function(event) {
  var req = event.request;

  // GET 以外はスルー（POST など API 送信はそのままネットワークへ）
  if (req.method !== 'GET') return;

  var url;
  try {
    url = new URL(req.url);
  } catch (e) {
    return; // 不正 URL はスルー
  }

  // http / https 以外（chrome-extension など）はスルー
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return;

  // /api/* はネットワークのみ（オフライン時は IndexedDB が代替）
  if (url.pathname.startsWith('/api/')) return;

  // ── ナビゲーションリクエスト（PWA 起動・ページ遷移）─────────
  if (req.mode === 'navigate') {
    event.respondWith(handleNavigate(req));
    return;
  }

  // ── その他リソース（画像・JS・アイコン等）───────────────────
  event.respondWith(handleAsset(req));
});

// ============================================================
// ナビゲーション処理（3段フォールバック）
// ============================================================
function handleNavigate(req) {
  return caches.open(CACHE_NAME).then(function(cache) {

    // 【段1】req の URL と完全一致で検索（root '/' がヒットするはず）
    return cache.match(req)
      .then(function(hit) {
        if (hit) {
          console.log('[SW v12] navigate HIT(1) exact:', req.url);
          scheduleUpdate(cache, req);
          return hit;
        }

        // 【段2】'./index.html' キーで直接検索
        return cache.match('./index.html')
          .then(function(hit2) {
            if (hit2) {
              console.log('[SW v12] navigate HIT(2) ./index.html');
              return hit2;
            }

            // 【段3】ネットワーク取得 → キャッシュ更新
            console.log('[SW v12] navigate MISS → network fetch');
            return fetch(req, { cache: 'no-cache' })
              .then(function(res) {
                if (res && res.ok) {
                  var c1 = res.clone(), c2 = res.clone();
                  cache.put(req,            c1);
                  cache.put('./index.html', c2);
                  console.log('[SW v12] navigate network OK → 2キーキャッシュ更新');
                }
                return res;
              })
              .catch(function() {
                // 完全オフライン かつ キャッシュ空 → 内蔵フォールバック HTML
                console.warn('[SW v12] navigate OFFLINE → OFFLINE_PAGE 返却');
                return new Response(OFFLINE_PAGE, {
                  status: 200,
                  headers: { 'Content-Type': 'text/html; charset=utf-8' }
                });
              });
          });
      });
  });
}

// ============================================================
// 通常アセット処理（Cache First）
// ============================================================
function handleAsset(req) {
  var url;
  try { url = new URL(req.url); } catch(e) { url = { pathname: '' }; }

  return caches.open(CACHE_NAME).then(function(cache) {
    return cache.match(req).then(function(hit) {
      if (hit) {
        // バックグラウンドで最新版を取得・更新
        scheduleUpdate(cache, req);
        return hit;
      }
      // キャッシュなし → ネットワーク → 保存
      return fetch(req)
        .then(function(res) {
          if (res && res.ok) {
            cache.put(req, res.clone());
          }
          return res;
        })
        .catch(function() {
          // ── オフライン時: リソース種別ごとに適切なレスポンスを返す ──
          var p = url.pathname;

          // JS ファイル → 空スクリプトを返す（エラーにしない）
          if (p.endsWith('.js')) {
            return new Response('/* offline */', {
              status: 200,
              headers: { 'Content-Type': 'application/javascript; charset=utf-8' }
            });
          }
          // CSS ファイル → 空スタイルを返す
          if (p.endsWith('.css')) {
            return new Response('/* offline */', {
              status: 200,
              headers: { 'Content-Type': 'text/css; charset=utf-8' }
            });
          }
          // 画像・アイコン → 1×1 透明 GIF を返す（404/503 回避）
          if (p.match(/\.(png|jpg|jpeg|gif|ico|svg|webp)$/i)) {
            var gif1x1 = 'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';
            var bin = atob(gif1x1);
            var arr = new Uint8Array(bin.length);
            for (var i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
            return new Response(arr.buffer, {
              status: 200,
              headers: { 'Content-Type': 'image/gif' }
            });
          }
          // その他は 503
          return new Response('', {
            status: 503,
            statusText: 'offline'
          });
        });
    });
  });
}

// ============================================================
// バックグラウンドキャッシュ更新（Stale-While-Revalidate）
// ============================================================
function scheduleUpdate(cache, req) {
  fetch(req).then(function(res) {
    if (!res || !res.ok) return;
    // navigate の場合は 2 キー更新
    if (req.mode === 'navigate') {
      var clone = res.clone();
      cache.put(req,            res);
      cache.put('./index.html', clone);
    } else {
      cache.put(req, res);
    }
  }).catch(function() { /* オフライン時は無視 */ });
}
