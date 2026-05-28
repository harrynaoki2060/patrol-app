"""
FastAPI 依存性注入（Dependency Injection）

認証・認可の共通ロジックを Depends として提供する。

使い方:
    from app.api.deps import get_current_active_user, require_admin

    @router.get("/sites")
    async def list_sites(user = Depends(require_admin)):
        ...

    @router.delete("/users/{id}")
    async def delete_user(user = Depends(require_super_admin)):
        ...

依存ツリー:
    get_current_user
        └── get_current_active_user
                ├── require_supervisor   (SUPERVISOR 以上)
                ├── require_admin        (ADMIN 以上)
                └── require_super_admin  (SUPER_ADMIN のみ)
"""
from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.admin_user import AdminRole, AdminUser
from app.repositories.admin_user import AdminUserRepository

logger = logging.getLogger(__name__)

# OAuth2 Bearer スキーム（Swagger UI に🔒アイコンが表示される）
_bearer_scheme = HTTPBearer(auto_error=True)

# 401 の統一エラー
_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="認証情報が無効です",
    headers={"WWW-Authenticate": "Bearer"},
)

_INACTIVE_ERROR = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="このアカウントは無効化されています",
)

_FORBIDDEN_ERROR = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="この操作を行う権限がありません",
)


# =============================================================================
# 基底 Depends
# =============================================================================

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    """
    Authorization: Bearer <token> ヘッダーを検証して AdminUser を返す。
    - トークンが無効または期限切れ → 401
    - DB にユーザーが存在しない → 401
    """
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise _CREDENTIALS_ERROR

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise _CREDENTIALS_ERROR

    repo = AdminUserRepository(db)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise _CREDENTIALS_ERROR

    return user


async def get_current_active_user(
    user: AdminUser = Depends(get_current_user),
) -> AdminUser:
    """
    有効なユーザーのみ通す。
    is_active=False の場合は 403 を返す。
    """
    if not user.is_active:
        raise _INACTIVE_ERROR
    return user


# =============================================================================
# ロール別 Depends
# =============================================================================

# ロール階層（数字が大きいほど権限が高い）
_ROLE_LEVEL = {
    AdminRole.SUPERVISOR.value: 1,
    AdminRole.ADMIN.value: 2,
    AdminRole.SUPER_ADMIN.value: 3,
}


def _require_role(min_role: str):
    """
    指定ロール以上のユーザーのみ通すファクトリ関数。
    """
    async def _dep(user: AdminUser = Depends(get_current_active_user)) -> AdminUser:
        user_level = _ROLE_LEVEL.get(user.role, 0)
        required_level = _ROLE_LEVEL.get(min_role, 999)
        if user_level < required_level:
            logger.warning(
                "Permission denied: user=%s role=%s required=%s",
                user.email, user.role, min_role,
            )
            raise _FORBIDDEN_ERROR
        return user

    # Swagger の description に表示するための名前を設定
    _dep.__name__ = f"require_{min_role}"
    return _dep


# 各ロール用 Depends（router で直接 Depends(require_admin) と書ける）
require_supervisor = _require_role(AdminRole.SUPERVISOR.value)
"""SUPERVISOR 以上（申請確認・承認系エンドポイント）"""

require_admin = _require_role(AdminRole.ADMIN.value)
"""ADMIN 以上（現場管理・QR 発行系エンドポイント）"""

require_super_admin = _require_role(AdminRole.SUPER_ADMIN.value)
"""SUPER_ADMIN のみ（管理者ユーザー管理・会社設定系エンドポイント）"""
