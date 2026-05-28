"""
Repository 層の動作確認テスト

確認項目:
  - Worker.create / get_by_id / get_by_phone_normalized / get_active_by_phone
  - Site.create / get_by_id / get_active_by_company / get_active_by_id
  - 重複電話番号での UniqueConstraint エラー
  - 論理削除（is_active=False）のフィルタ動作
"""
import uuid
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.site import SiteRepository
from app.repositories.worker import WorkerRepository


# =============================================================================
# ヘルパー
# =============================================================================

def _phone(suffix: str = "0001") -> tuple[str, str]:
    """テスト用電話番号を生成（表示用, 正規化済み）"""
    raw = f"090-1234-{suffix}"
    normalized = raw.replace("-", "")
    return raw, normalized


def _worker_kwargs(suffix: str = "0001") -> dict:
    """Worker 作成に必要な最低限のパラメータ"""
    raw, normalized = _phone(suffix)
    return {
        "phone": raw,
        "phone_normalized": normalized,
        "last_name": "田中",
        "first_name": f"太郎{suffix}",
        "birth_date": date(1990, 1, 1),
        "worker_type": "company_employee",
        "job_title": "大工",
        "consent_agreed_at": None,
        "is_active": True,
    }


def _site_kwargs(company_id: str, name_suffix: str = "A") -> dict:
    """Site 作成に必要な最低限のパラメータ"""
    return {
        "company_id": company_id,
        "name": f"テスト現場{name_suffix}",
        "require_health_check": True,
        "require_insurance": True,
        "is_active": True,
    }


# =============================================================================
# Worker テスト
# =============================================================================

class TestWorkerRepository:
    async def test_create_and_get_by_id(self, db_session: AsyncSession) -> None:
        """Worker を作成して ID で取得できる"""
        repo = WorkerRepository(db_session)
        worker = await repo.create(**_worker_kwargs("1001"))

        assert worker.id is not None
        assert len(worker.id) == 36  # UUID v4 形式

        fetched = await repo.get_by_id(worker.id)
        assert fetched is not None
        assert fetched.id == worker.id
        assert fetched.last_name == "田中"
        assert fetched.first_name == "太郎1001"

    async def test_get_by_id_not_found_returns_none(self, db_session: AsyncSession) -> None:
        """存在しない ID は None を返す"""
        repo = WorkerRepository(db_session)
        result = await repo.get_by_id(str(uuid.uuid4()))
        assert result is None

    async def test_get_by_phone_normalized(self, db_session: AsyncSession) -> None:
        """phone_normalized で作業員を検索できる"""
        repo = WorkerRepository(db_session)
        _, normalized = _phone("2001")
        await repo.create(**_worker_kwargs("2001"))

        found = await repo.get_by_phone_normalized(normalized)
        assert found is not None
        assert found.phone_normalized == normalized

    async def test_get_by_phone_normalized_not_found(self, db_session: AsyncSession) -> None:
        """存在しない電話番号は None を返す"""
        repo = WorkerRepository(db_session)
        result = await repo.get_by_phone_normalized("09000000000")
        assert result is None

    async def test_get_active_by_phone_returns_active_only(
        self, db_session: AsyncSession
    ) -> None:
        """is_active=False の作業員は get_active_by_phone で取得できない"""
        repo = WorkerRepository(db_session)
        _, normalized = _phone("3001")

        # is_active=False で作成
        inactive_kwargs = {**_worker_kwargs("3001"), "is_active": False}
        await repo.create(**inactive_kwargs)

        result = await repo.get_active_by_phone(normalized)
        assert result is None

    async def test_duplicate_phone_raises_integrity_error(
        self, db_session: AsyncSession
    ) -> None:
        """同じ電話番号を 2 件 INSERT すると UniqueConstraint エラーになる"""
        repo = WorkerRepository(db_session)
        await repo.create(**_worker_kwargs("4001"))
        await db_session.flush()

        with pytest.raises(IntegrityError):
            await repo.create(**_worker_kwargs("4001"))  # 同じ phone_normalized
            await db_session.flush()

    async def test_uuid_is_generated_automatically(self, db_session: AsyncSession) -> None:
        """ID が UUID v4 形式で自動生成される"""
        repo = WorkerRepository(db_session)
        w1 = await repo.create(**_worker_kwargs("5001"))
        w2 = await repo.create(**_worker_kwargs("5002"))

        assert w1.id != w2.id
        # UUID v4: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
        assert w1.id[14] == "4"  # バージョン番号
        assert w2.id[14] == "4"


# =============================================================================
# Site テスト
# =============================================================================

class TestSiteRepository:
    async def test_create_and_get_by_id(self, db_session: AsyncSession) -> None:
        """Site を作成して ID で取得できる"""
        repo = SiteRepository(db_session)
        company_id = str(uuid.uuid4())
        site = await repo.create(**_site_kwargs(company_id, "X"))

        assert site.id is not None
        fetched = await repo.get_by_id(site.id)
        assert fetched is not None
        assert fetched.name == "テスト現場X"
        assert fetched.company_id == company_id

    async def test_get_by_id_not_found(self, db_session: AsyncSession) -> None:
        """存在しない ID は None を返す"""
        repo = SiteRepository(db_session)
        result = await repo.get_by_id(str(uuid.uuid4()))
        assert result is None

    async def test_get_active_by_company(self, db_session: AsyncSession) -> None:
        """company_id で有効な現場一覧を取得できる"""
        repo = SiteRepository(db_session)
        company_id = str(uuid.uuid4())

        await repo.create(**_site_kwargs(company_id, "Y1"))
        await repo.create(**_site_kwargs(company_id, "Y2"))
        await repo.create(**{**_site_kwargs(company_id, "Y3"), "is_active": False})

        sites = await repo.get_active_by_company(company_id)
        assert len(sites) == 2
        names = {s.name for s in sites}
        assert "テスト現場Y1" in names
        assert "テスト現場Y2" in names
        assert "テスト現場Y3" not in names

    async def test_get_active_by_id_inactive_returns_none(
        self, db_session: AsyncSession
    ) -> None:
        """is_active=False の現場は get_active_by_id で取得できない"""
        repo = SiteRepository(db_session)
        company_id = str(uuid.uuid4())
        site = await repo.create(**{**_site_kwargs(company_id, "Z"), "is_active": False})

        result = await repo.get_active_by_id(site.id)
        assert result is None

    async def test_get_active_by_company_empty(self, db_session: AsyncSession) -> None:
        """該当する現場がない場合は空リストを返す"""
        repo = SiteRepository(db_session)
        result = await repo.get_active_by_company(str(uuid.uuid4()))
        assert result == []

    async def test_site_has_required_fields(self, db_session: AsyncSession) -> None:
        """作成した Site が必須フィールドを持つ"""
        repo = SiteRepository(db_session)
        company_id = str(uuid.uuid4())
        site = await repo.create(**_site_kwargs(company_id, "W"))

        assert site.require_health_check is True
        assert site.require_insurance is True
        assert site.is_active is True
        assert site.created_at is not None
        assert site.updated_at is not None
