"""
FastAPI アプリケーション エントリポイント

起動コマンド（開発）:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

API ドキュメント（開発時のみ）:
    http://localhost:8000/api/docs
"""
import logging
import logging.config
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from app.core import token_store
from app.core.config import settings
from app.api.health import router as health_router
from app.api.admin.auth import router as admin_auth_router
from app.api.admin.entries import router as admin_entries_router
from app.api.admin.sites import router as admin_sites_router
from app.api.admin.qr import router as admin_qr_router
from app.api.admin.ops import router as admin_ops_router
from app.api.public.qr import router as public_qr_router
from app.api.public.workers import router as public_workers_router
from app.api.public.entries import router as public_entries_router
from app.db.session import check_db_connection, engine
from app.middleware.logging import RequestLoggingMiddleware, request_id_var

# =============================================================================
# ログ設定
# =============================================================================
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format=_LOG_FORMAT,
    datefmt=_LOG_DATE_FORMAT,
)

# SQLAlchemy の過剰なログを抑制
logging.getLogger("sqlalchemy.engine").setLevel(
    logging.DEBUG if settings.LOG_LEVEL.upper() == "DEBUG" else logging.WARNING
)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

# uvicorn access log は RequestLoggingMiddleware で代替するため無効化
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# passlib の bcrypt 関連 WARNING を抑制（bcrypt バージョン差異の通知）
logging.getLogger("passlib").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)


# =============================================================================
# ライフサイクル
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ------------------------------------------------------------------ 起動
    logger.info("=" * 60)
    logger.info("アプリケーション起動中")
    logger.info("  サービス : %s v%s", settings.APP_TITLE, settings.APP_VERSION)
    logger.info("  ログレベル: %s", settings.LOG_LEVEL)
    logger.info("  CORS     : %s", settings.allowed_origins_list)

    db_result = await check_db_connection()
    if db_result["status"] == "ok":
        logger.info("  DB接続   : OK — %s", db_result.get("version", ""))
    else:
        logger.error("  DB接続   : FAILED — %s", db_result.get("error"))

    logger.info("アプリケーション起動完了")
    logger.info("=" * 60)

    yield

    # ------------------------------------------------------------------ 終了
    logger.info("=" * 60)
    logger.info("アプリケーション終了中...")
    await engine.dispose()
    await token_store.close()
    logger.info("アプリケーション終了完了")
    logger.info("=" * 60)


# =============================================================================
# FastAPI アプリケーション
# =============================================================================
app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    description=(
        "建設工事向け新規入場管理システムの REST API\n\n"
        "**認証方法**: `POST /api/admin/auth/login` で取得した "
        "`access_token` を `Authorization: Bearer <token>` ヘッダーにセットしてください。"
    ),
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


# =============================================================================
# ミドルウェア（登録順 = 外側から内側へ）
# =============================================================================

# 1. リクエストログ（最外層で全リクエストを計測）
app.add_middleware(RequestLoggingMiddleware)

# 2. CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


# =============================================================================
# ルーター登録
# =============================================================================

# ヘルスチェック (認証不要)
app.include_router(health_router, prefix="/api")

# 管理者認証 (認証不要: login / refresh)
app.include_router(admin_auth_router, prefix="/api/admin")

# 公開 QR 認証 (認証不要: QR トークン + PIN → entry_session 発行)
app.include_router(public_qr_router, prefix="/api/public")

# 公開 作業員検索 (entry_session 認証必須)
app.include_router(public_workers_router, prefix="/api/public")

# 公開 入場申請 Draft (entry_session 認証必須)
app.include_router(public_entries_router, prefix="/api/public")

# 管理者 入場申請審査 (access_token 認証必須 + require_supervisor 以上)
app.include_router(admin_entries_router, prefix="/api/admin")

# 管理者 現場管理 (access_token 認証必須 + require_supervisor 以上)
app.include_router(admin_sites_router, prefix="/api/admin")

# 管理者 QR コード管理 (access_token 認証必須 + require_supervisor 以上)
app.include_router(admin_qr_router, prefix="/api/admin")

# 管理者 運用・UX 改善 (access_token 認証必須 + require_supervisor 以上) — Phase 9
app.include_router(admin_ops_router, prefix="/api/admin")


# =============================================================================
# Swagger UI に Bearer 認証スキームを追加
# =============================================================================
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # セキュリティスキームを追加
    schema.setdefault("components", {})
    schema["components"].setdefault("securitySchemes", {})

    # 管理 API 用 Bearer（access_token）
    schema["components"]["securitySchemes"]["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "POST /api/admin/auth/login で取得した access_token を入力してください",
    }

    # 公開申請 API 用 Bearer（entry_session_token）
    schema["components"]["securitySchemes"]["EntrySessionAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "POST /api/public/qr/verify で取得した entry_session_token を入力してください",
    }

    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi  # type: ignore[method-assign]


# =============================================================================
# グローバル例外ハンドラ（未処理 5xx の統一レスポンス + 構造化エラーログ）
# =============================================================================

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    未処理の例外をキャッチして 500 を返す。

    - req_id を X-Request-ID ヘッダーに含める（nginx / フロントエンドとの紐付け）
    - スタックトレースを ERROR レベルでログに記録する
    - エラー詳細はクライアントに返さない（情報漏洩防止）
    """
    req_id = request_id_var.get("")
    logger.error(
        "Unhandled exception [req=%s] %s %s: %s",
        req_id,
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "内部エラーが発生しました。しばらく待ってから再試行してください。"},
        headers={"X-Request-ID": req_id} if req_id else {},
    )


# =============================================================================
# ルートエンドポイント
# =============================================================================
@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {"message": "建設工事 新規入場管理システム API", "docs": "/api/docs"}
