"""
Health API の動作確認テスト

確認項目:
  - GET /api/health → 200 OK、レスポンス形式
  - GET /api/health/full → 200、各サービスのステータス
  - X-Request-ID ヘッダーが返る
  - DB 未接続時の degraded 挙動

実行方法:
    docker compose exec backend pytest tests/test_health_api.py -v
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    """テスト用の非同期 HTTP クライアント"""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


class TestSimpleHealth:
    async def test_health_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/api/health")
        assert response.status_code == 200

    async def test_health_body_schema(self, client: AsyncClient) -> None:
        data = (await client.get("/api/health")).json()
        assert data["status"] == "ok"
        assert data["service"] == "entry-management-api"
        assert "version" in data
        assert "timestamp" in data

    async def test_health_has_request_id_header(self, client: AsyncClient) -> None:
        """RequestLoggingMiddleware が X-Request-ID を付与する"""
        response = await client.get("/api/health")
        assert "x-request-id" in response.headers


class TestFullHealth:
    async def test_full_health_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/api/health/full")
        # DB / Redis / MinIO のいずれかに繋がらなくても 200 を返す（degraded）
        assert response.status_code == 200

    async def test_full_health_has_checks_key(self, client: AsyncClient) -> None:
        data = (await client.get("/api/health/full")).json()
        assert "checks" in data
        checks = data["checks"]
        assert "database" in checks
        assert "redis" in checks
        assert "minio" in checks

    async def test_full_health_status_is_ok_or_degraded(
        self, client: AsyncClient
    ) -> None:
        data = (await client.get("/api/health/full")).json()
        assert data["status"] in ("ok", "degraded")

    async def test_full_health_db_connected(self, client: AsyncClient) -> None:
        """DB が起動していれば database.status == ok"""
        data = (await client.get("/api/health/full")).json()
        db = data["checks"]["database"]
        # Docker 環境であれば ok になる
        if db["status"] == "ok":
            assert "version" in db
            assert "PostgreSQL" in db["version"]
        else:
            # DB に繋がっていない場合は error であることを確認
            assert db["status"] == "error"
            assert "error" in db

    async def test_root_returns_message(self, client: AsyncClient) -> None:
        response = await client.get("/")
        assert response.status_code == 200
        assert "message" in response.json()
