"""
QR コード検証サービス

QR トークン → PIN 検証 → entry_session 発行 までの業務ロジックを担う。

セキュリティ設計:
  - QR 存在リーク最小化:
      * 見つからない / 無効 / 期限切れ / 現場無効 はすべて同一 401 エラーを返す
      * ブロック中のみ 429 を返す（QR は存在するが一時利用不可を示す）
  - PIN brute-force 保護:
      * PIN 失敗 max_attempts 回でブロック (blocked_until = now + QR_BLOCK_MINUTES)
      * ブロック中は PIN 検証を行わずに即時 429
  - タイミング攻撃対策:
      * pin_required=False の QR に PIN が送られても無視（処理時間を均一化するため
        bcrypt dummy verify は行わない。PIN 不要の QR は token のみで進む）
      * pin_required=True の QR で pin が None の場合も 401 で返す（存在リーク防止）
  - 監査ログ:
      * 成功・失敗を問わず structuredlog 互換の WARNING/INFO を出す
      * last_accessed_at は flush のみ（commit は呼び出し元が行う）

コミット戦略:
  - 各操作（last_accessed_at 更新 / failed_attempts 増加 / block）は flush のみ
  - verify() 内で 1 回だけ commit することでアトミックに確定する
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.config import settings
from app.core.security import create_entry_session_token, verify_password
from app.repositories.qr_code import QrCodeRepository
from app.schemas.qr import QrVerifyRequest, QrVerifyResponse
from app.schemas.site import PublicSiteInfo

logger = logging.getLogger(__name__)

# =============================================================================
# 統一エラー定数
# =============================================================================

# QR 無効系（存在リーク防止のため not-found / inactive / expired を区別しない）
_QR_INVALID_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="QRコードが無効または期限切れです",
    headers={"WWW-Authenticate": "Bearer"},
)

# PIN 誤り（ブロック前の失敗）
_PIN_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="QRコードまたはPINが正しくありません",
    headers={"WWW-Authenticate": "Bearer"},
)

# ブロック中（QR は存在するが一時利用不可）
_BLOCKED_ERROR = HTTPException(
    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
    detail="PIN の失敗回数が上限を超えました。しばらく待ってから再度お試しください",
    headers={"Retry-After": str(settings.QR_BLOCK_MINUTES * 60)},
)


# =============================================================================
# サービス
# =============================================================================

class QrVerifyService:
    """
    QR コード検証サービス。

    各リクエストごとにインスタンスを生成し、session を持ち回す。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = QrCodeRepository(session)

    async def verify(self, req: QrVerifyRequest) -> QrVerifyResponse:
        """
        QR トークン + PIN を検証して entry_session_token を発行する。

        処理順:
          1. token で QR コードを取得（site を eagerly load）
          2. QR / 現場の有効性チェック（無効なら統一 401）
          3. ブロックチェック（ブロック中なら 429）
          4. last_accessed_at を更新（flush）
          5. PIN 検証（pin_required=True の場合のみ）
             a. 成功: failed_attempts リセット（flush）
             b. 失敗: failed_attempts 増加 → 上限到達でブロック（flush）→ 401
          6. commit
          7. entry_session_token 発行 + レスポンス返却

        Raises:
            HTTPException 401: QR 無効 / PIN 誤り
            HTTPException 429: ブロック中
        """
        now = datetime.now(timezone.utc)

        # ------------------------------------------------------------------
        # 1. QR コード取得（site を JOIN 相当で eager load）
        # ------------------------------------------------------------------
        qr = await self.repo.get_by_token_with_site(req.token)

        if qr is None:
            logger.warning(
                "QR verify: token not found token=%.8s...",
                req.token,
            )
            raise _QR_INVALID_ERROR

        # ------------------------------------------------------------------
        # 2. QR / 現場の有効性チェック（同一エラーで返す）
        # ------------------------------------------------------------------

        # max_uses チェック（0以下の use_count は考慮しない）
        if qr.max_uses is not None and qr.use_count >= qr.max_uses:
            logger.warning(
                "QR verify: max_uses exceeded qr_id=%s use_count=%d max=%d",
                qr.id, qr.use_count, qr.max_uses,
            )
            raise _QR_INVALID_ERROR

        if not qr.is_active:
            logger.warning(
                "QR verify: inactive qr_id=%s site_id=%s",
                qr.id,
                qr.site_id,
            )
            raise _QR_INVALID_ERROR

        if qr.expires_at is not None and qr.expires_at < now:
            logger.warning(
                "QR verify: expired qr_id=%s expired_at=%s",
                qr.id,
                qr.expires_at.isoformat(),
            )
            raise _QR_INVALID_ERROR

        # site の有効性チェック（is_active + end_date）
        site = qr.site
        if site is None or not site.is_active:
            logger.warning(
                "QR verify: site inactive qr_id=%s site_id=%s",
                qr.id,
                qr.site_id,
            )
            raise _QR_INVALID_ERROR

        if site.end_date is not None and site.end_date < now.date():
            logger.warning(
                "QR verify: site ended qr_id=%s site_id=%s end_date=%s",
                qr.id,
                qr.site_id,
                site.end_date.isoformat(),
            )
            raise _QR_INVALID_ERROR

        # ------------------------------------------------------------------
        # 3. ブロックチェック（ブロック解除日時が未来なら 429）
        # ------------------------------------------------------------------
        if qr.blocked_until is not None and qr.blocked_until > now:
            remaining_s = int((qr.blocked_until - now).total_seconds())
            logger.warning(
                "QR verify: blocked qr_id=%s site_id=%s remaining_s=%d",
                qr.id,
                qr.site_id,
                remaining_s,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="PIN の失敗回数が上限を超えました。しばらく待ってから再度お試しください",
                headers={"Retry-After": str(remaining_s)},
            )

        # ------------------------------------------------------------------
        # 4. last_accessed_at を更新（audit 用。成功・失敗問わず記録）
        # ------------------------------------------------------------------
        await self.repo.update_last_accessed(qr, now)

        # ------------------------------------------------------------------
        # 5. PIN 検証
        # ------------------------------------------------------------------
        if qr.pin_required:
            if req.pin is None or qr.pin_hash is None:
                # pin 未送信 or DB に pin_hash が未登録（設定ミス）
                # どちらも PIN 誤りと同じエラーを返す（存在リーク防止）
                await self._handle_pin_failure(qr, now)
                await self.session.commit()
                raise _PIN_ERROR

            if not verify_password(req.pin, qr.pin_hash):
                await self._handle_pin_failure(qr, now)
                await self.session.commit()
                logger.warning(
                    "QR verify: pin failure qr_id=%s site_id=%s attempts=%d max=%d",
                    qr.id,
                    qr.site_id,
                    qr.failed_attempts,
                    qr.max_attempts,
                )
                raise _PIN_ERROR

            # PIN 成功 → failed_attempts リセット
            await self.repo.reset_failed_attempts(qr)

        # ------------------------------------------------------------------
        # 6. use_count インクリメント（認証成功）
        # ------------------------------------------------------------------
        await self.repo.increment_use_count(qr)

        # ------------------------------------------------------------------
        # 7. コミット（last_accessed_at + use_count + 必要なら reset）
        # ------------------------------------------------------------------
        await self.session.commit()

        # ------------------------------------------------------------------
        # 7. entry_session_token 発行
        # ------------------------------------------------------------------
        token = create_entry_session_token(
            site_id=qr.site_id,
            qr_code_id=qr.id,
        )

        logger.info(
            "QR verify: success qr_id=%s site_id=%s pin_required=%s use_count=%d",
            qr.id,
            qr.site_id,
            qr.pin_required,
            qr.use_count,
        )
        audit.qr_verify_success(qr_id=qr.id, site_id=qr.site_id, pin_required=qr.pin_required)

        return QrVerifyResponse(
            entry_session_token=token,
            expires_in=settings.ENTRY_SESSION_EXPIRE_MINUTES * 60,
            site=PublicSiteInfo(
                id=site.id,
                name=site.name,
                require_health_check=site.require_health_check,
                require_insurance=site.require_insurance,
                custom_notice=site.custom_notice,
            ),
        )

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    async def _handle_pin_failure(self, qr, now: datetime) -> None:
        """
        PIN 失敗時のカウント増加とブロック処理。

        failed_attempts をインクリメントし、max_attempts 以上に達したら
        blocked_until を設定する。flush のみ（commit は呼び出し元で行う）。
        """
        await self.repo.increment_failed_attempts(qr)

        if qr.failed_attempts >= qr.max_attempts:
            blocked_until = now + timedelta(minutes=settings.QR_BLOCK_MINUTES)
            await self.repo.block(qr, blocked_until)
            logger.warning(
                "QR blocked: qr_id=%s site_id=%s failures=%d until=%s",
                qr.id,
                qr.site_id,
                qr.failed_attempts,
                blocked_until.isoformat(),
            )
            audit.qr_verify_block(qr_id=qr.id, site_id=qr.site_id)
