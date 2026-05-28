"""
リクエストログミドルウェア

各リクエストに UUID ベースの request_id を付与し、
メソッド・パス・ステータスコード・処理時間をログに記録する。

Phase 8 追加:
  - 5xx レスポンスは ERROR レベル + exc_info でスタックトレースを記録
  - 4xx レスポンスは WARNING レベル
  - X-Request-ID を全レスポンスヘッダーに付与（フロントエンド・nginx ログとの紐付け用）

レスポンスヘッダーに X-Request-ID を含めるため、フロントエンドや
ロードバランサーからもリクエストを追跡できる。
"""
import logging
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# リクエスト ID をコンテキスト変数として保持（非同期コンテキスト内で参照可能）
# audit.py からもインポートされる
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    リクエストごとに一意の ID を付与してログに記録するミドルウェア。

    ログ出力例:
        INFO  GET /api/health 200 12.3ms [req=a1b2c3d4]
        WARN  POST /api/admin/auth/login 401 45.2ms [req=e5f6a7b8]
        ERROR POST /api/admin/sites 500 8.1ms [req=c9d0e1f2]
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # リクエスト ID を生成してコンテキスト変数に設定
        req_id = str(uuid.uuid4())[:8]
        request_id_var.set(req_id)

        start = time.perf_counter()
        response: Response | None = None
        exc_caught: BaseException | None = None

        try:
            response = await call_next(request)
            return response
        except Exception as e:
            exc_caught = e
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            status = response.status_code if response is not None else 500

            # ログレベル決定
            path = request.url.path
            if "/health" in path or "/nginx-health" in path:
                log_level = logging.DEBUG
            elif exc_caught is not None or status >= 500:
                # 未処理例外 or 5xx: ERROR レベル + スタックトレース
                log_level = logging.ERROR
            elif status >= 400:
                log_level = logging.WARNING
            else:
                log_level = logging.INFO

            logger.log(
                log_level,
                "%s %s %s %.1fms [req=%s]",
                request.method,
                path,
                status,
                elapsed_ms,
                req_id,
                exc_info=(exc_caught is not None),
            )

            # X-Request-ID をレスポンスヘッダーに付与
            if response is not None:
                response.headers["X-Request-ID"] = req_id
