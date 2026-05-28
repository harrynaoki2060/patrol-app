"""
QR コード検証基盤のテスト

確認項目:
  【security.py — entry_session token】
  - create_entry_session_token の payload
  - decode_entry_session_token の成功・失敗
  - access_token / refresh_token を entry_session デコーダが拒否すること
  - entry_session_token を access デコーダが拒否すること

  【QrVerifyService — 実 DB テスト】
  - PIN 不要 QR の正常認証
  - PIN 必要 QR の正常認証
  - トークン不一致 → 401 (存在リーク防止)
  - 無効 QR (is_active=False) → 401
  - 期限切れ QR → 401
  - 現場無効 (is_active=False) → 401
  - 現場工期終了 → 401
  - ブロック中 QR → 429
  - PIN 必要 QR で pin 未送信 → 401
  - PIN 不一致 → 401
  - PIN 失敗 → failed_attempts 増加
  - PIN 連続失敗 max_attempts 回 → ブロック発動
  - ブロック後は 429 を返す
  - last_accessed_at が更新される

  【public_deps.py — get_current_entry_session】
  - 有効な entry_session_token → payload を返す
  - 無効トークン → 401
  - access_token（type 違い）→ 401
  - payload に site_id なし → 401

  【API エンドポイント（httpx）】
  - POST /api/public/qr/verify 正常系（PIN なし）
  - POST /api/public/qr/verify 正常系（PIN あり）
  - POST /api/public/qr/verify 無効トークン → 401
  - POST /api/public/qr/verify PIN 誤り → 401
  - POST /api/public/qr/verify PIN が数字以外 → 422
  - entry_session_token で管理 API にアクセス → 401（逆流防止）

実行方法:
    make test-qr
    docker compose exec backend pytest tests/test_qr_verify.py -v
"""
from __future__ import annotations

import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from jose import jwt as jose_jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    TOKEN_TYPE_ENTRY_SESSION,
    create_access_token,
    create_entry_session_token,
    decode_access_token,
    decode_entry_session_token,
    hash_password,
)
from app.main import app
from app.models.company import Company
from app.models.qr_code import SiteQrCode
from app.models.site import Site
from app.schemas.qr import QrVerifyRequest
from app.services.qr_verify import QrVerifyService


# =============================================================================
# ヘルパー・ファクトリ
# =============================================================================

def _make_company() -> Company:
    return Company(
        id=str(uuid.uuid4()),
        name="テスト建設株式会社",
        is_active=True,
    )


def _make_site(company_id: str, *, is_active: bool = True, end_date: date | None = None) -> Site:
    return Site(
        id=str(uuid.uuid4()),
        company_id=company_id,
        name="テスト現場",
        require_health_check=True,
        require_insurance=True,
        is_active=is_active,
        end_date=end_date,
        custom_notice="安全帯を必ず着用してください",
    )


def _make_qr(
    site_id: str,
    *,
    pin: str | None = None,
    is_active: bool = True,
    expires_at: datetime | None = None,
    failed_attempts: int = 0,
    max_attempts: int = 3,
    blocked_until: datetime | None = None,
) -> SiteQrCode:
    """テスト用 SiteQrCode を生成する。pin が与えられた場合は bcrypt ハッシュ化する。"""
    return SiteQrCode(
        id=str(uuid.uuid4()),
        site_id=site_id,
        token=secrets.token_urlsafe(48),  # 64 文字相当
        pin_required=pin is not None,
        pin_hash=hash_password(pin) if pin is not None else None,
        is_active=is_active,
        expires_at=expires_at,
        failed_attempts=failed_attempts,
        max_attempts=max_attempts,
        blocked_until=blocked_until,
        label="テスト用 QR",
    )


async def _seed_site_with_qr(
    session: AsyncSession,
    *,
    pin: str | None = None,
    site_active: bool = True,
    site_end_date: date | None = None,
    qr_active: bool = True,
    qr_expires_at: datetime | None = None,
    failed_attempts: int = 0,
    max_attempts: int = 3,
    blocked_until: datetime | None = None,
) -> tuple[Site, SiteQrCode]:
    """Company → Site → SiteQrCode を DB に INSERT して返す。"""
    company = _make_company()
    session.add(company)
    await session.flush()

    site = _make_site(
        company.id,
        is_active=site_active,
        end_date=site_end_date,
    )
    session.add(site)
    await session.flush()

    qr = _make_qr(
        site.id,
        pin=pin,
        is_active=qr_active,
        expires_at=qr_expires_at,
        failed_attempts=failed_attempts,
        max_attempts=max_attempts,
        blocked_until=blocked_until,
    )
    session.add(qr)
    await session.flush()

    return site, qr


# =============================================================================
# 1. security.py — entry_session token
# =============================================================================

class TestEntrySessionToken:
    def test_payload_has_required_fields(self) -> None:
        """entry_session token の payload に必須フィールドが含まれること"""
        token = create_entry_session_token(site_id="site-1", qr_code_id="qr-1")
        payload = jose_jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        assert payload["type"] == TOKEN_TYPE_ENTRY_SESSION
        assert payload["site_id"] == "site-1"
        assert payload["qr_code_id"] == "qr-1"
        assert "jti" in payload
        assert "exp" in payload
        assert "iat" in payload

    def test_no_sub_field(self) -> None:
        """entry_session token には sub (user_id) が含まれないこと（最小 payload）"""
        token = create_entry_session_token(site_id="s1", qr_code_id="q1")
        payload = jose_jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        assert "sub" not in payload

    def test_expires_in_configured_minutes(self) -> None:
        """有効期限が設定値（ENTRY_SESSION_EXPIRE_MINUTES）通りであること"""
        token = create_entry_session_token(site_id="s1", qr_code_id="q1")
        payload = jose_jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        now = datetime.now(timezone.utc).timestamp()
        expected_expire = now + settings.ENTRY_SESSION_EXPIRE_MINUTES * 60
        assert abs(payload["exp"] - expected_expire) < 5

    def test_decode_entry_session_token_success(self) -> None:
        token = create_entry_session_token(site_id="s1", qr_code_id="q1")
        payload = decode_entry_session_token(token)
        assert payload is not None
        assert payload["site_id"] == "s1"
        assert payload["qr_code_id"] == "q1"

    def test_decode_entry_session_rejects_access_token(self) -> None:
        """access_token は entry_session デコーダに通らないこと"""
        access_token = create_access_token(
            user_id="u1", email="a@b.com", role="admin", name="X"
        )
        assert decode_entry_session_token(access_token) is None

    def test_decode_access_rejects_entry_session_token(self) -> None:
        """entry_session_token は access デコーダに通らないこと（管理 API 不正流用防止）"""
        entry_token = create_entry_session_token(site_id="s1", qr_code_id="q1")
        assert decode_access_token(entry_token) is None

    def test_decode_expired_entry_session_returns_none(self) -> None:
        """期限切れの entry_session_token は None を返すこと"""
        payload = {
            "type": TOKEN_TYPE_ENTRY_SESSION,
            "site_id": "s1",
            "qr_code_id": "q1",
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
            "jti": str(uuid.uuid4()),
        }
        expired_token = jose_jwt.encode(
            payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM
        )
        assert decode_entry_session_token(expired_token) is None

    def test_each_token_has_unique_jti(self) -> None:
        """トークンごとに一意の jti が発行されること"""
        t1 = create_entry_session_token(site_id="s1", qr_code_id="q1")
        t2 = create_entry_session_token(site_id="s1", qr_code_id="q1")
        p1 = jose_jwt.decode(t1, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        p2 = jose_jwt.decode(t2, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        assert p1["jti"] != p2["jti"]


# =============================================================================
# 2. QrVerifyService — 実 DB テスト
# =============================================================================

class TestQrVerifyServiceSuccess:
    async def test_verify_without_pin(self, db_session) -> None:
        """PIN 不要の QR コードは token のみで認証できる"""
        site, qr = await _seed_site_with_qr(db_session)
        service = QrVerifyService(db_session)

        result = await service.verify(QrVerifyRequest(token=qr.token, pin=None))

        assert result.entry_session_token != ""
        assert result.token_type == "bearer"
        assert result.expires_in == settings.ENTRY_SESSION_EXPIRE_MINUTES * 60
        assert result.site.id == site.id
        assert result.site.name == site.name
        assert result.site.require_health_check is True
        assert result.site.require_insurance is True
        assert result.site.custom_notice == "安全帯を必ず着用してください"

    async def test_verify_with_correct_pin(self, db_session) -> None:
        """PIN 必要 QR でも正しい PIN を送ると認証できる"""
        site, qr = await _seed_site_with_qr(db_session, pin="1234")
        service = QrVerifyService(db_session)

        result = await service.verify(QrVerifyRequest(token=qr.token, pin="1234"))

        assert result.entry_session_token != ""
        assert result.site.id == site.id

    async def test_verify_resets_failed_attempts_on_success(self, db_session) -> None:
        """正しい PIN で認証すると failed_attempts がリセットされる"""
        site, qr = await _seed_site_with_qr(
            db_session, pin="5678", failed_attempts=2
        )
        service = QrVerifyService(db_session)
        await service.verify(QrVerifyRequest(token=qr.token, pin="5678"))

        await db_session.refresh(qr)
        assert qr.failed_attempts == 0
        assert qr.blocked_until is None

    async def test_verify_updates_last_accessed_at(self, db_session) -> None:
        """verify 成功後に last_accessed_at が更新される"""
        _, qr = await _seed_site_with_qr(db_session)
        assert qr.last_accessed_at is None

        service = QrVerifyService(db_session)
        await service.verify(QrVerifyRequest(token=qr.token))

        await db_session.refresh(qr)
        assert qr.last_accessed_at is not None

    async def test_returned_entry_session_contains_correct_ids(self, db_session) -> None:
        """返却された entry_session_token の payload に正しい site_id / qr_code_id が含まれる"""
        site, qr = await _seed_site_with_qr(db_session)
        service = QrVerifyService(db_session)

        result = await service.verify(QrVerifyRequest(token=qr.token))

        payload = decode_entry_session_token(result.entry_session_token)
        assert payload is not None
        assert payload["site_id"] == site.id
        assert payload["qr_code_id"] == qr.id


class TestQrVerifyServiceErrors:
    async def test_unknown_token_raises_401(self, db_session) -> None:
        """存在しないトークンは 401（QR 存在リーク防止）"""
        service = QrVerifyService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.verify(QrVerifyRequest(token="no-such-token"))
        assert exc_info.value.status_code == 401

    async def test_inactive_qr_raises_401(self, db_session) -> None:
        """無効化された QR は 401（is_active=False）"""
        _, qr = await _seed_site_with_qr(db_session, qr_active=False)
        service = QrVerifyService(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.verify(QrVerifyRequest(token=qr.token))
        assert exc_info.value.status_code == 401

    async def test_expired_qr_raises_401(self, db_session) -> None:
        """期限切れ QR は 401"""
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        _, qr = await _seed_site_with_qr(db_session, qr_expires_at=past)
        service = QrVerifyService(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.verify(QrVerifyRequest(token=qr.token))
        assert exc_info.value.status_code == 401

    async def test_future_expiry_qr_succeeds(self, db_session) -> None:
        """有効期限が未来の QR は認証できる"""
        future = datetime.now(timezone.utc) + timedelta(days=7)
        _, qr = await _seed_site_with_qr(db_session, qr_expires_at=future)
        service = QrVerifyService(db_session)

        result = await service.verify(QrVerifyRequest(token=qr.token))
        assert result.entry_session_token != ""

    async def test_inactive_site_raises_401(self, db_session) -> None:
        """現場が無効 (is_active=False) の場合は 401"""
        _, qr = await _seed_site_with_qr(db_session, site_active=False)
        service = QrVerifyService(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.verify(QrVerifyRequest(token=qr.token))
        assert exc_info.value.status_code == 401

    async def test_ended_site_raises_401(self, db_session) -> None:
        """工期終了済みの現場は 401"""
        yesterday = date.today() - timedelta(days=1)
        _, qr = await _seed_site_with_qr(db_session, site_end_date=yesterday)
        service = QrVerifyService(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.verify(QrVerifyRequest(token=qr.token))
        assert exc_info.value.status_code == 401

    async def test_blocked_qr_raises_429(self, db_session) -> None:
        """ブロック中の QR は 429"""
        blocked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        _, qr = await _seed_site_with_qr(db_session, blocked_until=blocked_until)
        service = QrVerifyService(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.verify(QrVerifyRequest(token=qr.token))
        assert exc_info.value.status_code == 429
        assert "Retry-After" in exc_info.value.headers

    async def test_expired_block_is_cleared(self, db_session) -> None:
        """ブロック解除日時が過去の場合は 429 にならない（通常の認証を試みる）"""
        past_block = datetime.now(timezone.utc) - timedelta(minutes=1)
        _, qr = await _seed_site_with_qr(db_session, blocked_until=past_block)
        service = QrVerifyService(db_session)

        # ブロック解除後は通常通り認証できる
        result = await service.verify(QrVerifyRequest(token=qr.token))
        assert result.entry_session_token != ""

    async def test_pin_required_no_pin_raises_401(self, db_session) -> None:
        """PIN 必要 QR に pin を送らないと 401"""
        _, qr = await _seed_site_with_qr(db_session, pin="9999")
        service = QrVerifyService(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.verify(QrVerifyRequest(token=qr.token, pin=None))
        assert exc_info.value.status_code == 401

    async def test_pin_wrong_raises_401(self, db_session) -> None:
        """PIN 誤りは 401"""
        _, qr = await _seed_site_with_qr(db_session, pin="1111")
        service = QrVerifyService(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.verify(QrVerifyRequest(token=qr.token, pin="9999"))
        assert exc_info.value.status_code == 401


class TestQrBruteForceProtection:
    async def test_pin_failure_increments_failed_attempts(self, db_session) -> None:
        """PIN 失敗で failed_attempts が 1 増加する"""
        _, qr = await _seed_site_with_qr(db_session, pin="1111")
        service = QrVerifyService(db_session)

        with pytest.raises(HTTPException):
            await service.verify(QrVerifyRequest(token=qr.token, pin="0000"))

        await db_session.refresh(qr)
        assert qr.failed_attempts == 1

    async def test_reaching_max_attempts_sets_blocked_until(self, db_session) -> None:
        """max_attempts 回連続失敗すると blocked_until が設定される"""
        _, qr = await _seed_site_with_qr(db_session, pin="1111", max_attempts=3)
        service = QrVerifyService(db_session)

        for _ in range(3):
            with pytest.raises(HTTPException):
                await service.verify(QrVerifyRequest(token=qr.token, pin="0000"))

        await db_session.refresh(qr)
        assert qr.blocked_until is not None
        assert qr.blocked_until > datetime.now(timezone.utc)

    async def test_blocked_after_max_failures_returns_429(self, db_session) -> None:
        """max_attempts 回失敗後の次のリクエストは 429"""
        _, qr = await _seed_site_with_qr(db_session, pin="1111", max_attempts=2)
        service = QrVerifyService(db_session)

        # 2 回失敗してブロック
        for _ in range(2):
            with pytest.raises(HTTPException):
                await service.verify(QrVerifyRequest(token=qr.token, pin="0000"))

        # ブロック後は 429
        with pytest.raises(HTTPException) as exc_info:
            await service.verify(QrVerifyRequest(token=qr.token, pin="0000"))
        assert exc_info.value.status_code == 429

    async def test_block_duration_is_configured_minutes(self, db_session) -> None:
        """ブロック解除日時が設定値（QR_BLOCK_MINUTES）通りであること"""
        _, qr = await _seed_site_with_qr(db_session, pin="1111", max_attempts=1)
        service = QrVerifyService(db_session)

        before = datetime.now(timezone.utc)
        with pytest.raises(HTTPException):
            await service.verify(QrVerifyRequest(token=qr.token, pin="0000"))

        await db_session.refresh(qr)
        expected_unblock = before + timedelta(minutes=settings.QR_BLOCK_MINUTES)
        # 5 秒の誤差を許容
        assert abs((qr.blocked_until - expected_unblock).total_seconds()) < 5

    async def test_last_accessed_at_updated_on_failure(self, db_session) -> None:
        """PIN 失敗でも last_accessed_at は更新される（監査ログ用）"""
        _, qr = await _seed_site_with_qr(db_session, pin="1111")
        assert qr.last_accessed_at is None

        service = QrVerifyService(db_session)
        with pytest.raises(HTTPException):
            await service.verify(QrVerifyRequest(token=qr.token, pin="0000"))

        await db_session.refresh(qr)
        assert qr.last_accessed_at is not None


# =============================================================================
# 3. QrVerifyRequest — バリデーション
# =============================================================================

class TestQrVerifyRequestValidation:
    def test_pin_must_be_digits(self) -> None:
        """PIN にアルファベットを含む場合は ValidationError"""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            QrVerifyRequest(token="some-token", pin="abc4")

    def test_pin_too_short(self) -> None:
        """PIN が 4 文字未満は ValidationError"""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            QrVerifyRequest(token="some-token", pin="123")

    def test_pin_too_long(self) -> None:
        """PIN が 8 文字超は ValidationError"""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            QrVerifyRequest(token="some-token", pin="123456789")

    def test_valid_pin_4_digits(self) -> None:
        req = QrVerifyRequest(token="some-token", pin="1234")
        assert req.pin == "1234"

    def test_valid_pin_8_digits(self) -> None:
        req = QrVerifyRequest(token="some-token", pin="12345678")
        assert req.pin == "12345678"

    def test_none_pin_allowed(self) -> None:
        req = QrVerifyRequest(token="some-token", pin=None)
        assert req.pin is None


# =============================================================================
# 4. public_deps.py — get_current_entry_session
# =============================================================================

class TestGetCurrentEntrySession:
    async def test_valid_token_returns_payload(self) -> None:
        """有効な entry_session_token で payload が返る"""
        from app.api.public_deps import get_current_entry_session
        from fastapi.security import HTTPAuthorizationCredentials

        token = create_entry_session_token(site_id="site-abc", qr_code_id="qr-xyz")
        creds = HTTPAuthorizationCredentials(scheme="bearer", credentials=token)

        payload = await get_current_entry_session(credentials=creds)
        assert payload["site_id"] == "site-abc"
        assert payload["qr_code_id"] == "qr-xyz"

    async def test_invalid_token_raises_401(self) -> None:
        from app.api.public_deps import get_current_entry_session
        from fastapi.security import HTTPAuthorizationCredentials

        creds = HTTPAuthorizationCredentials(scheme="bearer", credentials="invalid.token")
        with pytest.raises(HTTPException) as exc_info:
            await get_current_entry_session(credentials=creds)
        assert exc_info.value.status_code == 401

    async def test_access_token_raises_401(self) -> None:
        """access_token（type="access"）は entry_session deps で拒否される"""
        from app.api.public_deps import get_current_entry_session
        from fastapi.security import HTTPAuthorizationCredentials

        access_token = create_access_token(
            user_id="u1", email="a@b.com", role="admin", name="X"
        )
        creds = HTTPAuthorizationCredentials(scheme="bearer", credentials=access_token)
        with pytest.raises(HTTPException) as exc_info:
            await get_current_entry_session(credentials=creds)
        assert exc_info.value.status_code == 401

    async def test_token_without_site_id_raises_401(self) -> None:
        """site_id が欠落したトークンは 401（改ざん対策）"""
        from app.api.public_deps import get_current_entry_session
        from fastapi.security import HTTPAuthorizationCredentials

        # site_id を意図的に除いた payload
        payload = {
            "type": TOKEN_TYPE_ENTRY_SESSION,
            # "site_id": "s1",   # ← 意図的に欠落
            "qr_code_id": "q1",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
            "jti": str(uuid.uuid4()),
        }
        token = jose_jwt.encode(
            payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM
        )
        creds = HTTPAuthorizationCredentials(scheme="bearer", credentials=token)
        with pytest.raises(HTTPException) as exc_info:
            await get_current_entry_session(credentials=creds)
        assert exc_info.value.status_code == 401


# =============================================================================
# 5. API エンドポイント テスト (httpx)
# =============================================================================

class TestQrVerifyEndpoint:
    async def test_verify_without_pin_returns_200(self, db_session) -> None:
        """PIN 不要 QR の正常系 → 200"""
        site, qr = await _seed_site_with_qr(db_session)

        async def override_get_db():
            yield db_session

        from app.db.session import get_db
        app.dependency_overrides[get_db] = override_get_db

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/public/qr/verify",
                    json={"token": qr.token},
                )
            assert resp.status_code == 200
            data = resp.json()
            assert "entry_session_token" in data
            assert data["token_type"] == "bearer"
            assert data["expires_in"] > 0
            assert data["site"]["id"] == site.id
            assert data["site"]["name"] == site.name
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_verify_with_correct_pin_returns_200(self, db_session) -> None:
        """PIN 必要 QR の正常系 → 200"""
        _, qr = await _seed_site_with_qr(db_session, pin="4321")

        async def override_get_db():
            yield db_session

        from app.db.session import get_db
        app.dependency_overrides[get_db] = override_get_db

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/public/qr/verify",
                    json={"token": qr.token, "pin": "4321"},
                )
            assert resp.status_code == 200
            assert "entry_session_token" in resp.json()
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_verify_invalid_token_returns_401(self, db_session) -> None:
        """存在しないトークン → 401"""
        async def override_get_db():
            yield db_session

        from app.db.session import get_db
        app.dependency_overrides[get_db] = override_get_db

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/public/qr/verify",
                    json={"token": "completely-unknown-token"},
                )
            assert resp.status_code == 401
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_verify_wrong_pin_returns_401(self, db_session) -> None:
        """PIN 誤り → 401"""
        _, qr = await _seed_site_with_qr(db_session, pin="1111")

        async def override_get_db():
            yield db_session

        from app.db.session import get_db
        app.dependency_overrides[get_db] = override_get_db

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/public/qr/verify",
                    json={"token": qr.token, "pin": "9999"},
                )
            assert resp.status_code == 401
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_verify_non_digit_pin_returns_422(self, db_session) -> None:
        """PIN が数字以外 → 422（バリデーションエラー）"""
        async def override_get_db():
            yield db_session

        from app.db.session import get_db
        app.dependency_overrides[get_db] = override_get_db

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/public/qr/verify",
                    json={"token": "some-token", "pin": "abcd"},
                )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_entry_session_token_rejected_by_admin_api(self, db_session) -> None:
        """
        entry_session_token を管理 API（GET /api/admin/auth/me）に使うと 401 になること。
        公開セッションから管理 API への逆流を防ぐ。
        """
        _, qr = await _seed_site_with_qr(db_session)

        async def override_get_db():
            yield db_session

        from app.db.session import get_db
        app.dependency_overrides[get_db] = override_get_db

        try:
            # まず QR 認証して entry_session_token を取得
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                verify_resp = await client.post(
                    "/api/public/qr/verify",
                    json={"token": qr.token},
                )
            assert verify_resp.status_code == 200
            entry_token = verify_resp.json()["entry_session_token"]

            # entry_session_token で管理 API にアクセス → 401
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                admin_resp = await client.get(
                    "/api/admin/auth/me",
                    headers={"Authorization": f"Bearer {entry_token}"},
                )
            assert admin_resp.status_code == 401
        finally:
            app.dependency_overrides.pop(get_db, None)
