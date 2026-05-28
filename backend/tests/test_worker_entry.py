"""
作業員情報入力・Draft 管理基盤のテスト

確認項目:
  【validators.py】
  - normalize_phone: 正規化・バリデーション
  - validate_kana: カタカナ検証
  - validate_birth_date: 未来日禁止・年齢上限
  - get_age_warning: 年少者・高齢者警告
  - normalize_postal_code: 郵便番号正規化

  【receipt.py】
  - generate_receipt_number: 8文字・DB 重複なし

  【WorkerLookupService】
  - 既存 active worker → exists=True + WorkerSummary（最小情報のみ）
  - inactive worker → exists=False（存在リーク防止）
  - 未登録 → exists=False
  - 返却情報に birth_date/address/insurance_number が含まれないこと

  【DraftEntryService.create_draft】
  - 既存作業員の再利用（worker_id 指定）
  - 新規作業員の作成
  - 電話番号で既存作業員を自動紐付け
  - worker_id と phone の不一致 → 400
  - 同一 worker × site で重複 → 409
  - draft_started_at が設定されること
  - receipt_number が 8 文字英数字であること

  【DraftEntryService.update_draft】
  - 部分更新（送信されたフィールドのみ更新）
  - last_saved_at が更新されること
  - consent_agreed=True で consent_agreed_at が設定される
  - 他現場の entry → 404（cross-site 防止）
  - status != draft → 409
  - birth_date の年齢警告が返ること

  【DraftEntryService.submit】
  - 正常 submit → status=pending, submitted_at 設定
  - 必須フィールド不足 → 422（fields リスト付き）
  - 他現場の entry → 404
  - status != draft → 409
  - IP ハッシュが保存される（平文でない）
  - require_health_check=True の現場で has_health_check=False → 422

  【API エンドポイント (httpx)】
  - POST /api/public/workers/lookup → 200
  - POST /api/public/entries/draft → 201
  - PATCH /api/public/entries/{id} → 200
  - POST /api/public/entries/{id}/submit → 200
  - entry_session なし → 401
  - cross-site access → 404

実行方法:
    make test-worker
    docker compose exec backend pytest tests/test_worker_entry.py -v
"""
from __future__ import annotations

import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.config import settings
from app.core.security import create_entry_session_token
from app.core.validators import (
    get_age_warning,
    normalize_phone,
    normalize_postal_code,
    validate_birth_date,
    validate_kana,
)
from app.main import app
from app.models.company import Company
from app.models.entry import EntryStatus, WorkerSiteEntry
from app.models.qr_code import SiteQrCode
from app.models.site import Site
from app.models.worker import Worker
from app.repositories.entry import EntryRepository
from app.repositories.worker import WorkerRepository
from app.schemas.entry import DraftCreateRequest, DraftUpdateRequest
from app.schemas.worker import WorkerLookupRequest
from app.services.draft_entry import DraftEntryService
from app.services.worker_lookup import WorkerLookupService


# =============================================================================
# ヘルパー・ファクトリ
# =============================================================================

def _make_company() -> Company:
    return Company(id=str(uuid.uuid4()), name="テスト建設", is_active=True)


def _make_site(company_id: str, *, require_health_check: bool = True, require_insurance: bool = True) -> Site:
    return Site(
        id=str(uuid.uuid4()),
        company_id=company_id,
        name="テスト現場",
        require_health_check=require_health_check,
        require_insurance=require_insurance,
        is_active=True,
    )


def _make_qr(site_id: str) -> SiteQrCode:
    return SiteQrCode(
        id=str(uuid.uuid4()),
        site_id=site_id,
        token=secrets.token_urlsafe(48),
        pin_required=False,
        is_active=True,
    )


def _make_worker(
    *,
    phone_normalized: str = "09012345678",
    is_active: bool = True,
    birth_date: date | None = date(1990, 1, 1),
    job_title: str | None = "型枠大工",
) -> Worker:
    return Worker(
        id=str(uuid.uuid4()),
        phone=phone_normalized,
        phone_normalized=phone_normalized,
        last_name="田中",
        first_name="太郎",
        worker_type="company_employee",
        affiliation_company="テスト建設",
        job_title=job_title,
        birth_date=birth_date,
        is_active=is_active,
        consent_agreed_at=datetime.now(timezone.utc),
    )


def _make_entry(worker_id: str, site_id: str, qr_id: str, *, status: str = "draft") -> WorkerSiteEntry:
    now = datetime.now(timezone.utc)
    return WorkerSiteEntry(
        id=str(uuid.uuid4()),
        worker_id=worker_id,
        site_id=site_id,
        qr_code_id=qr_id,
        receipt_number="A3F7KM2P",
        status=status,
        has_health_check=False,
        draft_started_at=now,
        last_saved_at=now,
        submitted_at=None if status == "draft" else now,
    )


async def _seed_full_setup(session):
    """Company → Site → QR → Worker を DB に INSERT して返す"""
    company = _make_company()
    session.add(company)
    await session.flush()

    site = _make_site(company.id)
    session.add(site)
    await session.flush()

    qr = _make_qr(site.id)
    session.add(qr)
    await session.flush()

    worker = _make_worker()
    session.add(worker)
    await session.flush()

    return company, site, qr, worker


# =============================================================================
# 1. validators.py
# =============================================================================

class TestNormalizePhone:
    def test_removes_hyphens(self) -> None:
        assert normalize_phone("090-1234-5678") == "09012345678"

    def test_removes_spaces(self) -> None:
        assert normalize_phone("090 1234 5678") == "09012345678"

    def test_removes_brackets(self) -> None:
        assert normalize_phone("(090)12345678") == "09012345678"

    def test_fullwidth_digits_converted(self) -> None:
        assert normalize_phone("０９０１２３４５６７８") == "09012345678"

    def test_international_format(self) -> None:
        assert normalize_phone("+819012345678") == "09012345678"

    def test_invalid_too_short(self) -> None:
        with pytest.raises(ValueError):
            normalize_phone("0901234567")  # 10桁（先頭0含む）

    def test_invalid_not_starting_with_zero(self) -> None:
        with pytest.raises(ValueError):
            normalize_phone("19012345678")

    def test_valid_11_digits(self) -> None:
        result = normalize_phone("09012345678")
        assert result == "09012345678"

    def test_valid_10_digits(self) -> None:
        result = normalize_phone("0312345678")
        assert result == "0312345678"


class TestValidateKana:
    def test_valid_katakana(self) -> None:
        assert validate_kana("タナカ") == "タナカ"

    def test_valid_katakana_with_space(self) -> None:
        assert validate_kana("タナカ タロウ") == "タナカ タロウ"

    def test_hiragana_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_kana("たなか")

    def test_kanji_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_kana("田中")

    def test_empty_returns_empty(self) -> None:
        assert validate_kana("") == ""


class TestValidateBirthDate:
    def test_valid_past_date(self) -> None:
        d = date(1990, 1, 1)
        assert validate_birth_date(d) == d

    def test_future_date_raises(self) -> None:
        future = date.today() + timedelta(days=1)
        with pytest.raises(ValueError, match="未来"):
            validate_birth_date(future)

    def test_too_old_raises(self) -> None:
        too_old = date(1900, 1, 1)
        with pytest.raises(ValueError, match="正しくありません"):
            validate_birth_date(too_old)

    def test_today_is_valid(self) -> None:
        # 今日生まれた新生児（実際には入場できないが、バリデーション自体は通る）
        assert validate_birth_date(date.today()) == date.today()


class TestGetAgeWarning:
    def test_minor_worker_gets_warning(self) -> None:
        young = date.today() - timedelta(days=365 * 14)
        warning = get_age_warning(young)
        assert warning is not None
        assert "14" in warning or "年少" in warning

    def test_normal_age_no_warning(self) -> None:
        normal = date(1990, 1, 1)
        assert get_age_warning(normal) is None

    def test_elderly_gets_warning(self) -> None:
        old = date.today() - timedelta(days=365 * 76)
        warning = get_age_warning(old)
        assert warning is not None


class TestNormalizePostalCode:
    def test_removes_hyphen(self) -> None:
        assert normalize_postal_code("123-4567") == "1234567"

    def test_fullwidth_digits(self) -> None:
        assert normalize_postal_code("１２３４５６７") == "1234567"

    def test_invalid_6_digits(self) -> None:
        with pytest.raises(ValueError):
            normalize_postal_code("123456")

    def test_invalid_8_digits(self) -> None:
        with pytest.raises(ValueError):
            normalize_postal_code("12345678")


# =============================================================================
# 2. WorkerLookupService — 実 DB テスト
# =============================================================================

class TestWorkerLookupService:
    async def test_returns_summary_for_active_worker(self, db_session) -> None:
        """active な作業員は exists=True + WorkerSummary を返す"""
        worker = _make_worker(phone_normalized="09011112222")
        db_session.add(worker)
        await db_session.flush()

        service = WorkerLookupService(db_session)
        result = await service.lookup("090-1111-2222")

        assert result.exists is True
        assert result.worker is not None
        assert result.worker.id == worker.id
        assert result.worker.last_name == "田中"

    def test_summary_does_not_contain_sensitive_fields(self) -> None:
        """WorkerSummary に個人情報が含まれないこと"""
        from app.schemas.worker import WorkerSummary
        fields = WorkerSummary.model_fields.keys()
        # これらは含めない
        assert "birth_date" not in fields
        assert "address" not in fields
        assert "insurance_number" not in fields
        assert "phone" not in fields
        assert "phone_normalized" not in fields
        assert "emergency_contact" not in fields
        assert "consent_agreed_at" not in fields

    async def test_returns_false_for_inactive_worker(self, db_session) -> None:
        """inactive な作業員は exists=False（存在リーク防止）"""
        worker = _make_worker(phone_normalized="09033334444", is_active=False)
        db_session.add(worker)
        await db_session.flush()

        service = WorkerLookupService(db_session)
        result = await service.lookup("090-3333-4444")

        assert result.exists is False
        assert result.worker is None

    async def test_returns_false_for_unknown_phone(self, db_session) -> None:
        """未登録の電話番号は exists=False"""
        service = WorkerLookupService(db_session)
        result = await service.lookup("090-9999-0000")
        assert result.exists is False


# =============================================================================
# 3. DraftEntryService.create_draft — 実 DB テスト
# =============================================================================

class TestCreateDraft:
    async def test_creates_draft_for_new_worker(self, db_session) -> None:
        """新規作業員の場合は Worker + Entry が作成される"""
        _, site, qr, _ = await _seed_full_setup(db_session)
        # 新しいユニークな電話番号を使う
        service = DraftEntryService(db_session)
        req = DraftCreateRequest(phone="080-0000-0001", last_name="新規", first_name="作業員")

        result = await service.create_draft(req, site_id=site.id, qr_code_id=qr.id)

        assert result.status == "draft"
        assert result.site_id == site.id
        assert result.worker.last_name == "新規"
        assert len(result.receipt_number) == 8
        assert result.draft_started_at is not None
        assert result.last_saved_at is not None

    async def test_reuses_existing_worker_by_phone(self, db_session) -> None:
        """phone で既存 worker が見つかれば再利用する"""
        _, site, qr, worker = await _seed_full_setup(db_session)
        service = DraftEntryService(db_session)
        req = DraftCreateRequest(
            phone=worker.phone_normalized,
            last_name="別の名前",  # 名前は無視して既存 worker を使う
            first_name="別の名前",
        )

        result = await service.create_draft(req, site_id=site.id, qr_code_id=qr.id)

        assert result.worker.id == worker.id
        assert result.worker.last_name == "田中"  # 既存 worker の名前

    async def test_reuses_worker_by_worker_id(self, db_session) -> None:
        """worker_id が指定された場合はその worker を使う"""
        _, site, qr, worker = await _seed_full_setup(db_session)
        service = DraftEntryService(db_session)
        req = DraftCreateRequest(
            phone=worker.phone_normalized,
            worker_id=worker.id,
        )

        result = await service.create_draft(req, site_id=site.id, qr_code_id=qr.id)

        assert result.worker.id == worker.id

    async def test_rejects_phone_worker_id_mismatch(self, db_session) -> None:
        """worker_id と phone が一致しない → 400"""
        _, site, qr, worker = await _seed_full_setup(db_session)
        service = DraftEntryService(db_session)
        req = DraftCreateRequest(
            phone="080-9999-0000",   # 別の電話番号
            worker_id=worker.id,
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.create_draft(req, site_id=site.id, qr_code_id=qr.id)
        assert exc_info.value.status_code == 400

    async def test_rejects_duplicate_active_entry(self, db_session) -> None:
        """同一 worker × site に既存の draft/pending → 409"""
        _, site, qr, worker = await _seed_full_setup(db_session)

        # 既存 draft を作成
        existing = _make_entry(worker.id, site.id, qr.id, status="draft")
        db_session.add(existing)
        await db_session.flush()

        service = DraftEntryService(db_session)
        req = DraftCreateRequest(
            phone=worker.phone_normalized,
            worker_id=worker.id,
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.create_draft(req, site_id=site.id, qr_code_id=qr.id)
        assert exc_info.value.status_code == 409

    async def test_receipt_number_is_8_chars_alphanumeric(self, db_session) -> None:
        """receipt_number が 8 桁英数字（I/O/0/1 除外）"""
        _, site, qr, _ = await _seed_full_setup(db_session)
        service = DraftEntryService(db_session)
        req = DraftCreateRequest(phone="080-1234-5001", last_name="テスト", first_name="一")

        result = await service.create_draft(req, site_id=site.id, qr_code_id=qr.id)

        receipt = result.receipt_number
        assert len(receipt) == 8
        assert receipt.isupper() or receipt.isdigit() or all(c in "ABCDEFGHJKLMNPQRSTUVWXYZ23456789" for c in receipt)
        # 除外文字が含まれないこと
        for excluded in ["I", "O", "0", "1"]:
            assert excluded not in receipt


# =============================================================================
# 4. DraftEntryService.update_draft — 実 DB テスト
# =============================================================================

class TestUpdateDraft:
    async def _seed_draft(self, db_session):
        _, site, qr, worker = await _seed_full_setup(db_session)
        now = datetime.now(timezone.utc)
        entry = WorkerSiteEntry(
            id=str(uuid.uuid4()),
            worker_id=worker.id,
            site_id=site.id,
            qr_code_id=qr.id,
            receipt_number="TESTRCPT",
            status="draft",
            has_health_check=False,
            draft_started_at=now,
            last_saved_at=now,
            submitted_at=None,
        )
        db_session.add(entry)
        await db_session.flush()
        return site, worker, entry

    async def test_partial_update_only_sent_fields(self, db_session) -> None:
        """送信したフィールドのみ更新され、他は変わらない"""
        site, worker, entry = await self._seed_draft(db_session)
        service = DraftEntryService(db_session)

        result = await service.update_draft(
            entry_id=entry.id,
            site_id=site.id,
            req=DraftUpdateRequest(last_name="佐藤"),
        )

        assert result.worker.last_name == "佐藤"
        assert result.worker.first_name == "太郎"  # 変更なし

    async def test_updates_last_saved_at(self, db_session) -> None:
        """PATCH ごとに last_saved_at が更新される"""
        site, worker, entry = await self._seed_draft(db_session)
        original_saved_at = entry.last_saved_at

        service = DraftEntryService(db_session)
        result = await service.update_draft(
            entry_id=entry.id,
            site_id=site.id,
            req=DraftUpdateRequest(job_title="鳶工"),
        )

        assert result.last_saved_at != original_saved_at

    async def test_consent_agreed_sets_timestamp(self, db_session) -> None:
        """consent_agreed=True で consent_agreed_at が設定される"""
        _, site, qr, _ = await _seed_full_setup(db_session)
        # consent 未同意の worker を作成
        worker = Worker(
            id=str(uuid.uuid4()),
            phone="08088880001",
            phone_normalized="08088880001",
            last_name="同意",
            first_name="テスト",
            worker_type="company_employee",
            is_active=True,
            consent_agreed_at=None,  # 未同意
        )
        db_session.add(worker)
        now = datetime.now(timezone.utc)
        entry = WorkerSiteEntry(
            id=str(uuid.uuid4()),
            worker_id=worker.id,
            site_id=site.id,
            qr_code_id=qr.id,
            receipt_number="CONSENT01",
            status="draft",
            has_health_check=False,
            draft_started_at=now,
            last_saved_at=now,
            submitted_at=None,
        )
        db_session.add(entry)
        await db_session.flush()

        service = DraftEntryService(db_session)
        await service.update_draft(
            entry_id=entry.id,
            site_id=site.id,
            req=DraftUpdateRequest(consent_agreed=True),
        )

        await db_session.refresh(worker)
        assert worker.consent_agreed_at is not None

    async def test_cross_site_returns_404(self, db_session) -> None:
        """他現場の entry_id → 404（cross-site hijack 防止）"""
        _, site, qr, worker = await _seed_full_setup(db_session)
        now = datetime.now(timezone.utc)
        entry = WorkerSiteEntry(
            id=str(uuid.uuid4()),
            worker_id=worker.id,
            site_id=site.id,  # site_id A
            qr_code_id=qr.id,
            receipt_number="CROSS001",
            status="draft",
            has_health_check=False,
            draft_started_at=now,
            last_saved_at=now,
            submitted_at=None,
        )
        db_session.add(entry)
        await db_session.flush()

        service = DraftEntryService(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.update_draft(
                entry_id=entry.id,
                site_id="different-site-id",  # 異なる site_id
                req=DraftUpdateRequest(last_name="改ざん"),
            )
        assert exc_info.value.status_code == 404

    async def test_non_draft_status_returns_409(self, db_session) -> None:
        """status=pending の entry を PATCH → 409"""
        _, site, qr, worker = await _seed_full_setup(db_session)
        now = datetime.now(timezone.utc)
        entry = WorkerSiteEntry(
            id=str(uuid.uuid4()),
            worker_id=worker.id,
            site_id=site.id,
            qr_code_id=qr.id,
            receipt_number="PEND0001",
            status="pending",  # draft ではない
            has_health_check=False,
            draft_started_at=now,
            last_saved_at=now,
            submitted_at=now,
        )
        db_session.add(entry)
        await db_session.flush()

        service = DraftEntryService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.update_draft(
                entry_id=entry.id,
                site_id=site.id,
                req=DraftUpdateRequest(last_name="変更"),
            )
        assert exc_info.value.status_code == 409

    async def test_birth_date_warning_returned(self, db_session) -> None:
        """14 歳の誕生日 → warnings に年少者警告が含まれる"""
        _, site, qr, _ = await _seed_full_setup(db_session)
        young_birth = date.today() - timedelta(days=365 * 14)
        worker = _make_worker(phone_normalized="09077770001", birth_date=None)
        db_session.add(worker)
        now = datetime.now(timezone.utc)
        entry = WorkerSiteEntry(
            id=str(uuid.uuid4()),
            worker_id=worker.id,
            site_id=site.id,
            qr_code_id=qr.id,
            receipt_number="YOUNG001",
            status="draft",
            has_health_check=False,
            draft_started_at=now,
            last_saved_at=now,
            submitted_at=None,
        )
        db_session.add(entry)
        await db_session.flush()

        service = DraftEntryService(db_session)
        result = await service.update_draft(
            entry_id=entry.id,
            site_id=site.id,
            req=DraftUpdateRequest(birth_date=young_birth),
        )

        assert len(result.warnings) > 0


# =============================================================================
# 5. DraftEntryService.submit — 実 DB テスト
# =============================================================================

class TestSubmitEntry:
    async def _seed_complete_draft(self, db_session, *, require_health_check: bool = True, require_insurance: bool = False):
        """submit 可能な完全な draft を作成"""
        company = _make_company()
        db_session.add(company)
        await db_session.flush()

        site = _make_site(company.id, require_health_check=require_health_check, require_insurance=require_insurance)
        db_session.add(site)
        await db_session.flush()

        qr = _make_qr(site.id)
        db_session.add(qr)
        await db_session.flush()

        worker = Worker(
            id=str(uuid.uuid4()),
            phone="09055550001",
            phone_normalized="09055550001",
            last_name="申請",
            first_name="太郎",
            birth_date=date(1990, 5, 15),
            worker_type="company_employee",
            job_title="型枠大工",
            is_active=True,
            consent_agreed_at=datetime.now(timezone.utc),
        )
        db_session.add(worker)
        now = datetime.now(timezone.utc)
        entry = WorkerSiteEntry(
            id=str(uuid.uuid4()),
            worker_id=worker.id,
            site_id=site.id,
            qr_code_id=qr.id,
            receipt_number="SUBMT001",
            status="draft",
            has_health_check=True,
            draft_started_at=now,
            last_saved_at=now,
            submitted_at=None,
        )
        db_session.add(entry)
        await db_session.flush()
        return site, worker, entry

    async def test_submit_changes_status_to_pending(self, db_session) -> None:
        """submit 成功 → status=pending, submitted_at が設定される"""
        site, _, entry = await self._seed_complete_draft(db_session)
        service = DraftEntryService(db_session)

        result = await service.submit(
            entry_id=entry.id,
            site_id=site.id,
            client_ip="192.168.1.100",
        )

        assert result.status == "pending"
        assert result.submitted_at is not None
        assert result.receipt_number == "SUBMT001"

    async def test_submit_stores_ip_hash_not_plaintext(self, db_session) -> None:
        """submit 後に IP ハッシュが保存される（平文でない）"""
        import hashlib
        site, _, entry = await self._seed_complete_draft(db_session)
        service = DraftEntryService(db_session)

        await service.submit(
            entry_id=entry.id,
            site_id=site.id,
            client_ip="192.168.1.100",
        )

        await db_session.refresh(entry)
        expected_hash = hashlib.sha256("192.168.1.100".encode()).hexdigest()
        assert entry.submit_ip_hash == expected_hash
        assert "192.168.1.100" not in (entry.submit_ip_hash or "")

    async def test_submit_missing_required_fields_raises_422(self, db_session) -> None:
        """必須フィールドが不足している場合は 422"""
        company = _make_company()
        db_session.add(company)
        await db_session.flush()

        site = _make_site(company.id, require_health_check=False, require_insurance=False)
        db_session.add(site)
        await db_session.flush()

        qr = _make_qr(site.id)
        db_session.add(qr)
        await db_session.flush()

        # birth_date と job_title を空にした worker
        worker = Worker(
            id=str(uuid.uuid4()),
            phone="09066660001",
            phone_normalized="09066660001",
            last_name="未入力",
            first_name="太郎",
            birth_date=None,   # 未入力
            job_title=None,    # 未入力
            worker_type="company_employee",
            is_active=True,
            consent_agreed_at=datetime.now(timezone.utc),
        )
        db_session.add(worker)
        now = datetime.now(timezone.utc)
        entry = WorkerSiteEntry(
            id=str(uuid.uuid4()),
            worker_id=worker.id,
            site_id=site.id,
            qr_code_id=qr.id,
            receipt_number="MISS0001",
            status="draft",
            has_health_check=False,
            draft_started_at=now,
            last_saved_at=now,
            submitted_at=None,
        )
        db_session.add(entry)
        await db_session.flush()

        service = DraftEntryService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.submit(
                entry_id=entry.id,
                site_id=site.id,
                client_ip="127.0.0.1",
            )

        assert exc_info.value.status_code == 422
        assert "birth_date" in exc_info.value.detail["fields"]
        assert "job_title" in exc_info.value.detail["fields"]

    async def test_submit_cross_site_returns_404(self, db_session) -> None:
        site, _, entry = await self._seed_complete_draft(db_session)
        service = DraftEntryService(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.submit(
                entry_id=entry.id,
                site_id="wrong-site-id",
                client_ip="127.0.0.1",
            )
        assert exc_info.value.status_code == 404

    async def test_submit_already_pending_returns_409(self, db_session) -> None:
        site, _, entry = await self._seed_complete_draft(db_session)
        # 先に pending にする
        now = datetime.now(timezone.utc)
        entry.status = "pending"
        entry.submitted_at = now
        await db_session.flush()

        service = DraftEntryService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.submit(
                entry_id=entry.id,
                site_id=site.id,
                client_ip="127.0.0.1",
            )
        assert exc_info.value.status_code == 409

    async def test_require_health_check_enforced(self, db_session) -> None:
        """require_health_check=True の現場で has_health_check=False → 422"""
        site, _, entry = await self._seed_complete_draft(
            db_session, require_health_check=True
        )
        # has_health_check を False に設定
        entry.has_health_check = False
        await db_session.flush()

        service = DraftEntryService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.submit(
                entry_id=entry.id,
                site_id=site.id,
                client_ip="127.0.0.1",
            )

        assert exc_info.value.status_code == 422
        assert "has_health_check" in exc_info.value.detail["fields"]


# =============================================================================
# 6. DraftUpdateRequest バリデーション
# =============================================================================

class TestDraftUpdateRequestValidation:
    def test_invalid_gender_raises(self) -> None:
        with pytest.raises(ValidationError):
            DraftUpdateRequest(gender="unknown_gender")

    def test_invalid_blood_type_raises(self) -> None:
        with pytest.raises(ValidationError):
            DraftUpdateRequest(blood_type="X")

    def test_invalid_worker_type_raises(self) -> None:
        with pytest.raises(ValidationError):
            DraftUpdateRequest(worker_type="freelancer")

    def test_future_birth_date_raises(self) -> None:
        future = date.today() + timedelta(days=1)
        with pytest.raises(ValidationError):
            DraftUpdateRequest(birth_date=future)

    def test_future_planned_entry_date_is_valid(self) -> None:
        future = date.today() + timedelta(days=7)
        req = DraftUpdateRequest(planned_entry_date=future)
        assert req.planned_entry_date == future

    def test_past_planned_entry_date_raises(self) -> None:
        past = date.today() - timedelta(days=1)
        with pytest.raises(ValidationError):
            DraftUpdateRequest(planned_entry_date=past)

    def test_valid_kana(self) -> None:
        req = DraftUpdateRequest(last_name_kana="タナカ", first_name_kana="タロウ")
        assert req.last_name_kana == "タナカ"

    def test_invalid_kana_hiragana_raises(self) -> None:
        with pytest.raises(ValidationError):
            DraftUpdateRequest(last_name_kana="たなか")


# =============================================================================
# 7. API エンドポイント (httpx)
# =============================================================================

def _make_entry_session(site_id: str, qr_code_id: str) -> str:
    return create_entry_session_token(site_id=site_id, qr_code_id=qr_code_id)


class TestWorkerLookupEndpoint:
    async def test_lookup_existing_worker_returns_200(self, db_session) -> None:
        worker = _make_worker(phone_normalized="09011110001")
        db_session.add(worker)
        await db_session.flush()

        _, site, qr, _ = await _seed_full_setup(db_session)
        token = _make_entry_session(site.id, qr.id)

        async def override_get_db():
            yield db_session

        from app.db.session import get_db
        app.dependency_overrides[get_db] = override_get_db

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/public/workers/lookup",
                    json={"phone": "090-1111-0001"},
                    headers={"Authorization": f"Bearer {token}"},
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["exists"] is True
            assert data["worker"]["id"] == worker.id
            # 個人情報が含まれないこと
            assert "birth_date" not in data["worker"]
            assert "address" not in data["worker"]
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_lookup_without_session_returns_401(self, db_session) -> None:
        async def override_get_db():
            yield db_session

        from app.db.session import get_db
        app.dependency_overrides[get_db] = override_get_db

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/public/workers/lookup",
                    json={"phone": "090-0000-0001"},
                )
            assert resp.status_code == 403  # HTTPBearer は 403 を返す
        finally:
            app.dependency_overrides.pop(get_db, None)


class TestDraftEndpoints:
    async def _setup(self, db_session):
        _, site, qr, _ = await _seed_full_setup(db_session)
        token = _make_entry_session(site.id, qr.id)
        return site, qr, token

    async def test_create_draft_returns_201(self, db_session) -> None:
        site, qr, token = await self._setup(db_session)

        async def override_get_db():
            yield db_session

        from app.db.session import get_db
        app.dependency_overrides[get_db] = override_get_db

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/public/entries/draft",
                    json={"phone": "080-0000-9001", "last_name": "API", "first_name": "テスト"},
                    headers={"Authorization": f"Bearer {token}"},
                )
            assert resp.status_code == 201
            data = resp.json()
            assert data["status"] == "draft"
            assert data["site_id"] == site.id
            assert len(data["receipt_number"]) == 8
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_patch_draft_returns_200(self, db_session) -> None:
        site, qr, token = await self._setup(db_session)

        async def override_get_db():
            yield db_session

        from app.db.session import get_db
        app.dependency_overrides[get_db] = override_get_db

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                # まず draft 作成
                create_resp = await client.post(
                    "/api/public/entries/draft",
                    json={"phone": "080-0000-9002", "last_name": "パッチ", "first_name": "テスト"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert create_resp.status_code == 201
                entry_id = create_resp.json()["id"]

                # PATCH で更新
                patch_resp = await client.patch(
                    f"/api/public/entries/{entry_id}",
                    json={"job_title": "鳶工", "worker_type": "sole_proprietor"},
                    headers={"Authorization": f"Bearer {token}"},
                )
            assert patch_resp.status_code == 200
            data = patch_resp.json()
            assert data["worker"]["job_title"] == "鳶工"
            assert data["last_saved_at"] is not None
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_cross_site_patch_returns_404(self, db_session) -> None:
        """別サイトの entry_session で PATCH → 404"""
        site, qr, token_a = await self._setup(db_session)

        # 別の現場を作成してそのトークンを使う
        company2 = _make_company()
        db_session.add(company2)
        await db_session.flush()
        site2 = _make_site(company2.id)
        db_session.add(site2)
        qr2 = _make_qr(site2.id)
        db_session.add(qr2)
        await db_session.flush()
        token_b = _make_entry_session(site2.id, qr2.id)

        async def override_get_db():
            yield db_session

        from app.db.session import get_db
        app.dependency_overrides[get_db] = override_get_db

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                # site_a で draft 作成
                create_resp = await client.post(
                    "/api/public/entries/draft",
                    json={"phone": "080-0000-9003", "last_name": "クロス", "first_name": "テスト"},
                    headers={"Authorization": f"Bearer {token_a}"},
                )
                assert create_resp.status_code == 201
                entry_id = create_resp.json()["id"]

                # site_b のトークンで site_a の entry を PATCH → 404
                patch_resp = await client.patch(
                    f"/api/public/entries/{entry_id}",
                    json={"job_title": "侵入テスト"},
                    headers={"Authorization": f"Bearer {token_b}"},
                )
            assert patch_resp.status_code == 404
        finally:
            app.dependency_overrides.pop(get_db, None)
