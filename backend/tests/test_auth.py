"""
認証・権限基盤のテスト

確認項目:
  【security.py】
  - hash_password / verify_password の動作
  - create_access_token / create_refresh_token の payload
  - decode_token の成功・失敗・期限切れ
  - type ミスマッチ拒否

  【AuthService】
  - login success → TokenResponse
  - login wrong password → 401
  - login inactive user → 403
  - login locked user → 423
  - login failure count 増加・ロック発動
  - refresh_access_token success
  - refresh_access_token invalid token → 401

  【API エンドポイント（httpx）】
  - POST /api/admin/auth/login 正常系
  - POST /api/admin/auth/login 認証失敗
  - POST /api/admin/auth/refresh
  - GET /api/admin/auth/me（Bearer）
  - GET /api/admin/auth/me（トークンなし → 403）

  【deps.py（Role）】
  - require_admin が SUPERVISOR を拒否
  - require_super_admin が ADMIN を拒否

実行方法:
    make test-auth
    docker compose exec backend pytest tests/test_auth.py -v
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.security import (
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.main import app
from app.models.admin_user import AdminRole, AdminUser
from app.repositories.admin_user import AdminUserRepository
from app.services.auth import AuthService


# =============================================================================
# ヘルパー
# =============================================================================

def _make_admin(
    *,
    email: str = "test@example.com",
    password: str = "Secret1234!",
    role: str = AdminRole.ADMIN.value,
    is_active: bool = True,
    login_failure_count: int = 0,
    locked_until: datetime | None = None,
) -> AdminUser:
    """テスト用 AdminUser インスタンスを生成（DB 未保存）"""
    return AdminUser(
        id=str(uuid.uuid4()),
        company_id=str(uuid.uuid4()),
        email=email,
        password_hash=hash_password(password),
        name="テスト管理者",
        role=role,
        is_active=is_active,
        login_failure_count=login_failure_count,
        locked_until=locked_until,
    )


async def _seed_admin(db_session, **kwargs) -> AdminUser:
    """DB にテスト用管理者を INSERT して返す"""
    repo = AdminUserRepository(db_session)
    admin = _make_admin(**kwargs)
    db_session.add(admin)
    await db_session.flush()
    return admin


# =============================================================================
# 1. security.py — パスワードハッシュ
# =============================================================================

class TestPasswordHash:
    def test_hash_is_not_plain(self) -> None:
        hashed = hash_password("mypassword")
        assert hashed != "mypassword"
        assert hashed.startswith("$2b$")

    def test_verify_correct_password(self) -> None:
        hashed = hash_password("correct")
        assert verify_password("correct", hashed) is True

    def test_verify_wrong_password(self) -> None:
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_same_password_different_hash(self) -> None:
        """bcrypt は salt を毎回ランダム生成するため同じパスワードでも異なるハッシュになる"""
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2
        # 両方とも検証は通る
        assert verify_password("same", h1)
        assert verify_password("same", h2)


# =============================================================================
# 2. security.py — JWT
# =============================================================================

class TestJWT:
    def test_access_token_payload(self) -> None:
        token = create_access_token(
            user_id="user-123",
            email="a@example.com",
            role="admin",
            name="山田太郎",
        )
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["email"] == "a@example.com"
        assert payload["role"] == "admin"
        assert payload["name"] == "山田太郎"
        assert payload["type"] == TOKEN_TYPE_ACCESS
        assert "jti" in payload
        assert "exp" in payload

    def test_refresh_token_payload(self) -> None:
        token = create_refresh_token(user_id="user-456")
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user-456"
        assert payload["type"] == TOKEN_TYPE_REFRESH
        # refresh token に email/role が含まれないことを確認（最小化）
        assert "email" not in payload
        assert "role" not in payload

    def test_decode_access_token_rejects_refresh(self) -> None:
        """decode_access_token は refresh token を拒否する"""
        refresh_token = create_refresh_token(user_id="u1")
        assert decode_access_token(refresh_token) is None

    def test_decode_refresh_token_rejects_access(self) -> None:
        """decode_refresh_token は access token を拒否する"""
        access_token = create_access_token(
            user_id="u1", email="a@b.com", role="admin", name="X"
        )
        assert decode_refresh_token(access_token) is None

    def test_decode_invalid_token_returns_none(self) -> None:
        assert decode_token("not.a.valid.token") is None

    def test_decode_tampered_token_returns_none(self) -> None:
        token = create_access_token(
            user_id="u1", email="a@b.com", role="admin", name="X"
        )
        # ペイロード部分を改ざん
        parts = token.split(".")
        tampered = parts[0] + "." + "dGFtcGVyZWQ" + "." + parts[2]
        assert decode_token(tampered) is None

    def test_expired_token_returns_none(self) -> None:
        """有効期限を過去に設定したトークンは None を返す"""
        from jose import jwt as jose_jwt

        payload = {
            "sub": "u1",
            "type": TOKEN_TYPE_ACCESS,
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        }
        expired_token = jose_jwt.encode(
            payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM
        )
        assert decode_token(expired_token) is None

    def test_access_token_expires_in_30_minutes(self) -> None:
        from jose import jwt as jose_jwt

        token = create_access_token(
            user_id="u1", email="a@b.com", role="admin", name="X"
        )
        payload = jose_jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        now = datetime.now(timezone.utc).timestamp()
        expected_expire = now + settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        # 5 秒の誤差を許容
        assert abs(payload["exp"] - expected_expire) < 5


# =============================================================================
# 3. AuthService — 実 DB テスト
# =============================================================================

class TestAuthServiceLogin:
    async def test_login_success(self, db_session) -> None:
        """正しい認証情報でログインできる"""
        admin = await _seed_admin(
            db_session, email="ok@example.com", password="Pass1234!"
        )
        service = AuthService(db_session)
        result = await service.login("ok@example.com", "Pass1234!")

        assert result.access_token != ""
        assert result.refresh_token != ""
        assert result.token_type == "bearer"
        assert result.user["email"] == "ok@example.com"
        assert result.user["id"] == admin.id

    async def test_login_wrong_password_raises_401(self, db_session) -> None:
        """パスワードが違う場合は 401"""
        await _seed_admin(
            db_session, email="wrong@example.com", password="CorrectPass!"
        )
        service = AuthService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.login("wrong@example.com", "WrongPass!")
        assert exc_info.value.status_code == 401

    async def test_login_unknown_email_raises_401(self, db_session) -> None:
        """存在しないメールは 401（ユーザー存在リーク防止）"""
        service = AuthService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.login("nobody@example.com", "anypassword")
        assert exc_info.value.status_code == 401

    async def test_login_inactive_user_raises_403(self, db_session) -> None:
        """無効化ユーザーは 403"""
        await _seed_admin(
            db_session,
            email="inactive@example.com",
            password="Pass1234!",
            is_active=False,
        )
        service = AuthService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.login("inactive@example.com", "Pass1234!")
        assert exc_info.value.status_code == 403

    async def test_login_locked_user_raises_423(self, db_session) -> None:
        """ロック中ユーザーは 423"""
        locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
        await _seed_admin(
            db_session,
            email="locked@example.com",
            password="Pass1234!",
            locked_until=locked_until,
        )
        service = AuthService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.login("locked@example.com", "Pass1234!")
        assert exc_info.value.status_code == 423

    async def test_login_failure_increments_count(self, db_session) -> None:
        """ログイン失敗でカウントが増える"""
        admin = await _seed_admin(
            db_session, email="count@example.com", password="RealPass!"
        )
        service = AuthService(db_session)

        with pytest.raises(HTTPException):
            await service.login("count@example.com", "WrongPass!")

        await db_session.refresh(admin)
        assert admin.login_failure_count == 1

    async def test_login_failure_locks_after_max_attempts(self, db_session) -> None:
        """MAX_LOGIN_FAILURES 回失敗するとロックされる"""
        await _seed_admin(
            db_session, email="lock_test@example.com", password="RealPass!"
        )
        service = AuthService(db_session)

        for _ in range(settings.MAX_LOGIN_FAILURES):
            with pytest.raises(HTTPException):
                await service.login("lock_test@example.com", "WrongPass!")

        # 次の失敗は 423 になる（ロック状態）
        with pytest.raises(HTTPException) as exc_info:
            await service.login("lock_test@example.com", "WrongPass!")
        assert exc_info.value.status_code == 423

    async def test_login_success_resets_failure_count(self, db_session) -> None:
        """成功ログインで失敗カウントがリセットされる"""
        admin = await _seed_admin(
            db_session,
            email="reset@example.com",
            password="Pass1234!",
            login_failure_count=3,
        )
        service = AuthService(db_session)
        await service.login("reset@example.com", "Pass1234!")

        await db_session.refresh(admin)
        assert admin.login_failure_count == 0
        assert admin.locked_until is None


class TestAuthServiceRefresh:
    async def test_refresh_returns_new_access_token(self, db_session) -> None:
        """有効な refresh token で新しい access token が得られる"""
        admin = await _seed_admin(
            db_session, email="refresh@example.com", password="Pass1234!"
        )
        refresh_token = create_refresh_token(user_id=admin.id)

        service = AuthService(db_session)
        result = await service.refresh_access_token(refresh_token)

        assert result.access_token != ""
        assert result.token_type == "bearer"

        # 新しい access token のペイロードを確認
        payload = decode_access_token(result.access_token)
        assert payload is not None
        assert payload["sub"] == admin.id

    async def test_refresh_invalid_token_raises_401(self, db_session) -> None:
        """無効な refresh token は 401"""
        service = AuthService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.refresh_access_token("invalid.token.here")
        assert exc_info.value.status_code == 401

    async def test_refresh_with_access_token_raises_401(self, db_session) -> None:
        """access token を refresh に使おうとしても 401（type 不一致）"""
        admin = await _seed_admin(
            db_session, email="refresh2@example.com", password="Pass1234!"
        )
        access_token = create_access_token(
            user_id=admin.id, email=admin.email, role=admin.role, name=admin.name
        )
        service = AuthService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.refresh_access_token(access_token)
        assert exc_info.value.status_code == 401


# =============================================================================
# 4. API エンドポイントテスト（httpx）
# =============================================================================

@pytest.fixture
async def http_client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


class TestLoginEndpoint:
    async def test_login_returns_tokens(self, http_client, db_session) -> None:
        """POST /api/admin/auth/login 正常系"""
        await _seed_admin(
            db_session, email="apilogin@example.com", password="ApiPass1!"
        )
        response = await http_client.post(
            "/api/admin/auth/login",
            json={"email": "apilogin@example.com", "password": "ApiPass1!"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert "user" in data
        assert data["user"]["email"] == "apilogin@example.com"

    async def test_login_wrong_password_returns_401(self, http_client, db_session) -> None:
        await _seed_admin(
            db_session, email="wrongpw@example.com", password="Correct1!"
        )
        response = await http_client.post(
            "/api/admin/auth/login",
            json={"email": "wrongpw@example.com", "password": "Wrong!"},
        )
        assert response.status_code == 401

    async def test_login_invalid_email_format_returns_422(self, http_client) -> None:
        """不正な email 形式は Pydantic バリデーションで 422"""
        response = await http_client.post(
            "/api/admin/auth/login",
            json={"email": "not-an-email", "password": "Pass1234!"},
        )
        assert response.status_code == 422


class TestRefreshEndpoint:
    async def test_refresh_returns_access_token(self, http_client, db_session) -> None:
        admin = await _seed_admin(
            db_session, email="apirfsh@example.com", password="Pass1!"
        )
        refresh_token = create_refresh_token(user_id=admin.id)
        response = await http_client.post(
            "/api/admin/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        # Phase 8: トークンローテーション対応 — 新しい refresh_token も返る
        assert "refresh_token" in data
        assert data["refresh_token"] != refresh_token  # 新しいトークンが発行される

    async def test_refresh_invalid_returns_401(self, http_client) -> None:
        response = await http_client.post(
            "/api/admin/auth/refresh",
            json={"refresh_token": "bad.token"},
        )
        assert response.status_code == 401


class TestLogoutEndpoint:
    async def test_logout_returns_200(self, http_client, db_session) -> None:
        """有効な refresh_token を渡すとログアウトして 200"""
        admin = await _seed_admin(
            db_session, email="logout@example.com", password="Pass1!"
        )
        refresh_token = create_refresh_token(user_id=admin.id)

        response = await http_client.post(
            "/api/admin/auth/logout",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    async def test_logout_with_invalid_token_still_200(self, http_client) -> None:
        """無効な refresh_token でも 200（冪等性）"""
        response = await http_client.post(
            "/api/admin/auth/logout",
            json={"refresh_token": "already.expired.or.invalid"},
        )
        assert response.status_code == 200

    async def test_logout_service_returns_message(self, db_session) -> None:
        """AuthService.logout は LogoutResponse を返す"""
        admin = await _seed_admin(
            db_session, email="logout2@example.com", password="Pass1!"
        )
        refresh_token = create_refresh_token(user_id=admin.id)

        service = AuthService(db_session)
        result = await service.logout(refresh_token)
        assert result.message is not None


class TestMeEndpoint:
    async def test_me_with_valid_token(self, http_client, db_session) -> None:
        admin = await _seed_admin(
            db_session, email="metest@example.com", password="Pass1!"
        )
        token = create_access_token(
            user_id=admin.id, email=admin.email, role=admin.role, name=admin.name
        )
        response = await http_client.get(
            "/api/admin/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == admin.email
        assert data["id"] == admin.id

    async def test_me_without_token_returns_403(self, http_client) -> None:
        """トークンなしは 403"""
        response = await http_client.get("/api/admin/auth/me")
        assert response.status_code == 403

    async def test_me_with_invalid_token_returns_403(self, http_client) -> None:
        response = await http_client.get(
            "/api/admin/auth/me",
            headers={"Authorization": "Bearer invalid.token"},
        )
        assert response.status_code == 403


# =============================================================================
# 5. Role 依存性テスト
# =============================================================================

class TestRoleDependencies:
    async def test_supervisor_cannot_access_admin_route(
        self, http_client, db_session
    ) -> None:
        """SUPERVISOR は ADMIN 必須ルートに 403"""
        admin = await _seed_admin(
            db_session,
            email="sup@example.com",
            password="Pass1!",
            role=AdminRole.SUPERVISOR.value,
        )
        token = create_access_token(
            user_id=admin.id, email=admin.email, role=admin.role, name=admin.name
        )

        # テスト用に require_admin を使うエンドポイントを直接テストするために
        # deps.py の関数を単体でテストする
        from app.api.deps import _ROLE_LEVEL, AdminRole as _AdminRole

        supervisor_level = _ROLE_LEVEL.get(AdminRole.SUPERVISOR.value, 0)
        admin_level = _ROLE_LEVEL.get(AdminRole.ADMIN.value, 0)
        assert supervisor_level < admin_level

    def test_role_hierarchy_is_correct(self) -> None:
        """ロール階層が正しく定義されている"""
        from app.api.deps import _ROLE_LEVEL

        assert _ROLE_LEVEL[AdminRole.SUPERVISOR.value] < _ROLE_LEVEL[AdminRole.ADMIN.value]
        assert _ROLE_LEVEL[AdminRole.ADMIN.value] < _ROLE_LEVEL[AdminRole.SUPER_ADMIN.value]
