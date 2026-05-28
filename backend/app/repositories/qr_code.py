"""
QR Code Repository

QR コードの検索・状態更新を提供する。

設計方針:
  - `get_by_token_with_site` は site を JOIN で取得（N+1 防止）
  - ブルートフォース保護のカウンタ更新は flush のみ（呼び出し元が commit する）
  - token の存在リークを防ぐため、invalid/inactive の区別を行わない get_* は内部専用
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.qr_code import SiteQrCode
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class QrCodeRepository(BaseRepository[SiteQrCode]):
    model = SiteQrCode

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    # -------------------------------------------------------------------------
    # 検索（公開側）
    # -------------------------------------------------------------------------

    async def get_by_token_with_site(self, token: str) -> SiteQrCode | None:
        """
        トークンで QR コードを取得（site を eager load）。
        有効・無効問わず返す（サービス層で状態チェックを行う）。
        """
        result = await self.session.execute(
            select(SiteQrCode)
            .options(selectinload(SiteQrCode.site))
            .where(SiteQrCode.token == token)
        )
        return result.scalar_one_or_none()

    async def get_active_by_site(self, site_id: str) -> list[SiteQrCode]:
        """現場 ID で有効な QR コード一覧を取得（管理画面用）"""
        result = await self.session.execute(
            select(SiteQrCode).where(
                SiteQrCode.site_id == site_id,
                SiteQrCode.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    # -------------------------------------------------------------------------
    # 検索（管理側）
    # -------------------------------------------------------------------------

    async def get_all_by_site(self, site_id: str) -> list[SiteQrCode]:
        """
        現場 ID で全 QR コード（有効・無効含む）を取得し、
        creator（管理者名表示用）を eager load する。
        """
        result = await self.session.execute(
            select(SiteQrCode)
            .options(selectinload(SiteQrCode.creator))
            .where(SiteQrCode.site_id == site_id)
            .order_by(SiteQrCode.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id_with_site(self, qr_id: str) -> SiteQrCode | None:
        """QR ID で取得し site を eager load（管理側スコープチェック用）"""
        result = await self.session.execute(
            select(SiteQrCode)
            .options(selectinload(SiteQrCode.site))
            .where(SiteQrCode.id == qr_id)
        )
        return result.scalar_one_or_none()

    # -------------------------------------------------------------------------
    # 作成
    # -------------------------------------------------------------------------

    async def create_qr(
        self,
        *,
        site_id: str,
        pin_hash: str | None,
        pin_required: bool,
        label: str | None,
        expires_at: datetime | None,
        max_uses: int | None,
        created_by: str,
    ) -> SiteQrCode:
        """QR コードを新規作成する（token は自動生成）"""
        token = secrets.token_urlsafe(32)  # 43 文字の URL-safe Base64
        qr = SiteQrCode(
            site_id=site_id,
            token=token,
            pin_hash=pin_hash,
            pin_required=pin_required,
            label=label,
            expires_at=expires_at,
            max_uses=max_uses,
            created_by=created_by,
        )
        self.session.add(qr)
        await self.session.flush()
        return qr

    # -------------------------------------------------------------------------
    # 更新
    # -------------------------------------------------------------------------

    async def update_fields(self, qr: SiteQrCode, **fields: Any) -> None:
        """指定フィールドを更新して flush する"""
        for key, value in fields.items():
            setattr(qr, key, value)
        await self.session.flush()

    # -------------------------------------------------------------------------
    # ブルートフォース保護
    # -------------------------------------------------------------------------

    async def increment_failed_attempts(self, qr: SiteQrCode) -> None:
        """PIN 失敗回数を 1 増やす"""
        qr.failed_attempts += 1
        await self.session.flush()

    async def reset_failed_attempts(self, qr: SiteQrCode) -> None:
        """PIN 成功時: 失敗回数とブロックをリセット"""
        qr.failed_attempts = 0
        qr.blocked_until = None
        await self.session.flush()

    async def block(self, qr: SiteQrCode, blocked_until: datetime) -> None:
        """失敗回数が上限に達した場合: ブロック日時を設定 + blocked_count 累積"""
        qr.blocked_until = blocked_until
        qr.blocked_count += 1
        await self.session.flush()
        logger.warning(
            "QR blocked: id=%s token=%.8s... until=%s (total_blocks=%d)",
            qr.id, qr.token, blocked_until.isoformat(), qr.blocked_count,
        )

    # -------------------------------------------------------------------------
    # アクセス記録・無効化・有効化
    # -------------------------------------------------------------------------

    async def update_last_accessed(self, qr: SiteQrCode, accessed_at: datetime) -> None:
        """最終アクセス日時を更新（成功・失敗問わず記録）"""
        qr.last_accessed_at = accessed_at
        await self.session.flush()

    async def increment_use_count(self, qr: SiteQrCode) -> None:
        """QR 認証成功時に use_count を増やす"""
        qr.use_count += 1
        await self.session.flush()

    async def deactivate(
        self,
        qr: SiteQrCode,
        deactivated_by: str,
        deactivated_at: datetime,
    ) -> None:
        """QR コードを無効化する（削除はしない）"""
        qr.is_active = False
        qr.deactivated_by = deactivated_by
        qr.deactivated_at = deactivated_at
        await self.session.flush()
        logger.info(
            "QR deactivated: id=%s token=%.8s... by=%s",
            qr.id, qr.token, deactivated_by,
        )

    async def activate(self, qr: SiteQrCode) -> None:
        """無効化された QR コードを再有効化する"""
        qr.is_active = True
        qr.deactivated_by = None
        qr.deactivated_at = None
        await self.session.flush()
        logger.info(
            "QR activated: id=%s token=%.8s...",
            qr.id, qr.token,
        )
