"""
認証サービス

ログイン・トークン発行・リフレッシュ・ログアウトの業務ロジックを担う。
Repository（DB アクセス）と Security（JWT/bcrypt）を組み合わせる。

セキュリティ設計:
  - 認証失敗時のエラーメッセージは統一（ユーザー存在リーク防止）
  - ロック中でも bcrypt 検証を行わない（早期 return でサイドチャネル軽減）
  - 失敗カウントはロック後もリセットしない（ロック解除後に再カウント）
  - Phase 8: refresh token ローテーション + Redis jti 失効管理
    旧 refresh token は使用後に Redis に失効登録される（TTL = 残り有効期限）
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core import token_store
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    verify_password,
)
from app.models.admin_user import AdminUser
from app.repositories.admin_user import AdminUserRepository
from app.schemas.auth import LogoutResponse, TokenResponse, TokenRotationResponse

logger = logging.getLogger(__name__)

# 認証失敗時の統一エラーメッセージ（メール存在リーク防止）
_AUTH_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="メールアドレスまたはパスワードが正しくありません",
    headers={"WWW-Authenticate": "Bearer"},
)

_LOCKED_ERROR = HTTPException(
    status_code=status.HTTP_423_LOCKED,
    detail="アカウントが一時的にロックされています。しばらく待ってから再試行してください",
)

_INACTIVE_ERROR = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="このアカウントは無効化されています。管理者にお問い合わせください",
)

_REFRESH_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="リフレッシュトークンが無効または期限切れです",
    headers={"WWW-Authenticate": "Bearer"},
)


class AuthService:
    """認証サービス。インスタンスは各リクエストで生成する（session スコープ）"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AdminUserRepository(session)

    # -------------------------------------------------------------------------
    # ログイン
    # -------------------------------------------------------------------------

    async def login(
        self,
        email: str,
        password: str,
        ip: str | None = None,
    ) -> TokenResponse:
        """
        メール・パスワードで認証してトークンペアを返す。

        処理順:
          1. メールで AdminUser を取得（存在しなければ統一エラー）
          2. 無効化チェック（is_active=False → 403）
          3. ロックチェック（locked_until が未来 → 423）
          4. パスワード検証（失敗 → カウント増加・必要ならロック → 統一エラー）
          5. 成功 → カウントリセット・最終ログイン更新・トークン発行
          6. 監査ログ記録
        """
        now = datetime.now(timezone.utc)

        # 1. ユーザー取得（存在しなくても 401 の統一エラーを返す）
        user = await self.repo.get_by_email(email)
        if user is None:
            # タイミング攻撃対策: ユーザーが存在しない場合も bcrypt と同等の時間を消費
            verify_password("dummy", "$2b$12$KIXa1xb.aNIHrfqXfnzmuOf8cIHf.FyqsVq2v5eDMDRPOmVSbRdim")
            audit.login_failure(email, ip=ip, reason="user_not_found")
            raise _AUTH_ERROR

        # 2. 無効化チェック
        if not user.is_active:
            logger.warning("Inactive user login attempt: %s", email)
            audit.login_inactive(email, ip=ip)
            raise _INACTIVE_ERROR

        # 3. ロックチェック
        if user.locked_until is not None and user.locked_until > now:
            remaining = int((user.locked_until - now).total_seconds() / 60)
            logger.warning(
                "Locked account login attempt: %s (remaining %d min)", email, remaining
            )
            audit.login_locked(email, ip=ip)
            raise _LOCKED_ERROR

        # 4. パスワード検証
        if not verify_password(password, user.password_hash):
            await self._handle_login_failure(user, now)
            audit.login_failure(email, ip=ip, reason="bad_password")
            raise _AUTH_ERROR

        # 5. 成功処理
        await self.repo.reset_login_failure(user)
        await self.repo.update_last_login(user, now)
        await self.session.commit()

        logger.info("Login success: %s (role=%s)", email, user.role)
        audit.login_success(email, user_id=user.id, role=user.role, ip=ip)

        return TokenResponse(
            access_token=create_access_token(
                user_id=user.id,
                email=user.email,
                role=user.role,
                name=user.name,
            ),
            refresh_token=create_refresh_token(user_id=user.id),
            user={
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.role,
            },
        )

    async def _handle_login_failure(self, user: AdminUser, now: datetime) -> None:
        """ログイン失敗時のカウント増加とロック処理"""
        await self.repo.increment_login_failure(user)

        if user.login_failure_count >= settings.MAX_LOGIN_FAILURES:
            locked_until = now + timedelta(minutes=settings.ACCOUNT_LOCK_MINUTES)
            await self.repo.set_locked_until(user, locked_until)
            logger.warning(
                "Account locked: %s (failures=%d, until=%s)",
                user.email,
                user.login_failure_count,
                locked_until.isoformat(),
            )

        await self.session.commit()

    # -------------------------------------------------------------------------
    # トークンリフレッシュ（Phase 8: ローテーション + Redis 失効管理）
    # -------------------------------------------------------------------------

    async def refresh_access_token(self, refresh_token: str) -> TokenRotationResponse:
        """
        リフレッシュトークンを検証してアクセストークン + 新 refresh_token を発行する。

        Phase 8 変更点:
          - 旧 jti が Redis の失効リストにないことを確認（revoke 検出）
          - 新しい refresh_token を発行（ローテーション）
          - 旧 refresh_token の jti を Redis に登録（使用済みとしてブロック）
          - 監査ログ記録

        注意:
          - DB からユーザー情報を再取得して最新の role / name を使う
          - Redis エラー時はトークンを有効として扱う（可用性優先）
        """
        payload = decode_refresh_token(refresh_token)
        if payload is None:
            raise _REFRESH_ERROR

        jti: str = payload.get("jti", "")
        exp: int = payload.get("exp", 0)

        # Redis 失効チェック（再利用・ログアウト済みトークンの拒否）
        if jti and await token_store.is_revoked(jti):
            logger.warning(
                "Revoked refresh token used: jti=%.8s user_id=%s",
                jti, payload.get("sub", ""),
            )
            raise _REFRESH_ERROR

        user_id: str = payload.get("sub", "")
        user = await self.repo.get_by_id(user_id)

        if user is None or not user.is_active:
            raise _REFRESH_ERROR

        # 新トークンペアを発行
        new_access = create_access_token(
            user_id=user.id,
            email=user.email,
            role=user.role,
            name=user.name,
        )
        new_refresh = create_refresh_token(user_id=user.id)

        # 旧 refresh token を失効リストに登録（ローテーション）
        if jti:
            await token_store.revoke_token(jti, exp)

        logger.info("Token refreshed: %s", user.email)
        audit.token_refresh(user.id, user.email)

        return TokenRotationResponse(
            access_token=new_access,
            refresh_token=new_refresh,
        )

    # -------------------------------------------------------------------------
    # ログアウト（Phase 8: refresh token 即時失効）
    # -------------------------------------------------------------------------

    async def logout(self, refresh_token: str) -> LogoutResponse:
        """
        リフレッシュトークンを失効リストに登録してログアウトする。

        - 無効な/期限切れトークンが送られてきても 200 を返す（冪等性）
        - jti を Redis に登録して以降の refresh を拒否する
        - 監査ログを記録する
        """
        payload = decode_refresh_token(refresh_token)

        if payload is not None:
            jti: str = payload.get("jti", "")
            exp: int = payload.get("exp", 0)
            user_id: str = payload.get("sub", "")

            if jti:
                await token_store.revoke_token(jti, exp)

            # 監査ログ: ユーザー情報を取得（失敗しても無視）
            try:
                user = await self.repo.get_by_id(user_id)
                if user:
                    logger.info("Logout: %s", user.email)
                    audit.logout(user.id, user.email)
            except Exception:  # noqa: BLE001
                pass

        return LogoutResponse()
