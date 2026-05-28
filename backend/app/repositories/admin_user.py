"""
AdminUser Repository

認証に必要なデータアクセスを提供する。
ログイン失敗カウント・ロック・最終ログイン日時の更新は
「UPDATE のみ」で済む軽量操作にする（ORM SELECT + setattr + flush）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_user import AdminUser
from app.repositories.base import BaseRepository


class AdminUserRepository(BaseRepository[AdminUser]):
    model = AdminUser

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    # -------------------------------------------------------------------------
    # 検索
    # -------------------------------------------------------------------------

    async def get_by_email(self, email: str) -> AdminUser | None:
        """メールアドレスで管理者を取得する（大文字小文字区別なし）"""
        result = await self.session.execute(
            select(AdminUser).where(
                AdminUser.email == email.lower().strip()
            )
        )
        return result.scalar_one_or_none()

    async def get_active_by_email(self, email: str) -> AdminUser | None:
        """有効な管理者のみをメールアドレスで取得する"""
        result = await self.session.execute(
            select(AdminUser).where(
                AdminUser.email == email.lower().strip(),
                AdminUser.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    # -------------------------------------------------------------------------
    # ログイン失敗管理
    # -------------------------------------------------------------------------

    async def increment_login_failure(self, user: AdminUser) -> None:
        """ログイン失敗カウントを 1 増やす"""
        user.login_failure_count += 1
        await self.session.flush()

    async def reset_login_failure(self, user: AdminUser) -> None:
        """ログイン成功時にカウントとロックをリセットする"""
        user.login_failure_count = 0
        user.locked_until = None
        await self.session.flush()

    async def set_locked_until(self, user: AdminUser, locked_until: datetime) -> None:
        """アカウントをロックする（locked_until まで）"""
        user.locked_until = locked_until
        await self.session.flush()

    async def update_last_login(self, user: AdminUser, login_at: datetime) -> None:
        """最終ログイン日時を更新する"""
        user.last_login_at = login_at
        await self.session.flush()
