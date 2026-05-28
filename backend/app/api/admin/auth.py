"""
管理者認証 API

POST /api/admin/auth/login   → ログイン（access + refresh トークン発行）
POST /api/admin/auth/refresh → アクセストークン再発行（トークンローテーション）
POST /api/admin/auth/logout  → ログアウト（refresh token 即時失効）
GET  /api/admin/auth/me      → 現在のユーザー情報取得
"""
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.admin_user import CurrentUserSchema
from app.schemas.auth import (
    LogoutRequest,
    LogoutResponse,
    RefreshRequest,
    LoginRequest,
    TokenResponse,
    TokenRotationResponse,
)
from app.services.auth import AuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["admin-auth"])


def _get_client_ip(request: Request) -> str | None:
    """クライアント IP を取得（リバースプロキシ経由の場合は X-Forwarded-For を使用）"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return None


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="管理者ログイン",
    description=(
        "メールアドレスとパスワードで認証し、アクセストークンとリフレッシュトークンを返す。\n\n"
        "- ログイン失敗が連続 5 回でアカウントが 30 分ロックされる\n"
        "- ロック中は 423 Locked を返す\n"
        "- 無効化されたアカウントは 403 を返す\n"
        "- 監査ログに成功・失敗・ロックを記録する"
    ),
)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    管理者ログイン。

    成功時は access_token（30分）と refresh_token（7日）を返す。
    失敗時は統一メッセージ（ユーザー存在リーク防止）。
    """
    req_id = request.headers.get("x-request-id", "")
    ip = _get_client_ip(request)
    logger.info("Login attempt: email=%s ip=%s [req=%s]", body.email, ip, req_id)

    service = AuthService(db)
    return await service.login(body.email, body.password, ip=ip)


@router.post(
    "/refresh",
    response_model=TokenRotationResponse,
    summary="アクセストークン再発行（トークンローテーション）",
    description=(
        "リフレッシュトークンを使ってアクセストークンと新しいリフレッシュトークンを返す。\n\n"
        "- 旧リフレッシュトークンは即時失効する（再利用不可）\n"
        "- 失効済みトークン・期限切れトークンは 401\n"
        "- アクセストークンの有効期限は 30 分"
    ),
)
async def refresh_token(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenRotationResponse:
    """
    リフレッシュトークンでアクセストークンを再発行する。

    Phase 8: トークンローテーション対応。
    旧トークンは Redis に登録されて失効するため、同じトークンでの再リフレッシュは不可。
    フロントエンドは返却された新しい refresh_token を保存すること。
    """
    service = AuthService(db)
    return await service.refresh_access_token(body.refresh_token)


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="ログアウト（リフレッシュトークン失効）",
    description=(
        "リフレッシュトークンを即時失効させる。\n\n"
        "- 成功・失敗問わず 200 を返す（冪等性）\n"
        "- 失効後は同じリフレッシュトークンでの再発行が不可になる\n"
        "- フロントエンドは sessionStorage からトークンを削除すること"
    ),
)
async def logout(
    body: LogoutRequest,
    db: AsyncSession = Depends(get_db),
) -> LogoutResponse:
    """
    ログアウト処理。refresh_token の jti を Redis に失効登録する。
    """
    service = AuthService(db)
    return await service.logout(body.refresh_token)


@router.get(
    "/me",
    response_model=CurrentUserSchema,
    summary="現在のユーザー情報",
    description="Bearer トークンから認証されたユーザーの情報を返す。",
)
async def get_me(
    current_user: AdminUser = Depends(get_current_active_user),
) -> CurrentUserSchema:
    """
    認証済みユーザーの情報を返す。
    トークンが有効で is_active=True の場合のみ成功する。
    """
    return CurrentUserSchema.model_validate(current_user)
