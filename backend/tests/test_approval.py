"""
管理者側 承認・審査フローのテスト

確認項目:
  【state_machine】
  - 許可される遷移（draft→pending, pending→approved, pending→rejected, pending→withdrawn）
  - 禁止される遷移（draft→approved, approved→pending, rejected→approved 等）
  - assert_can_transition: 不正遷移は 409

  【SiteRepository.get_site_ids_for_user】
  - SUPER_ADMIN → None（全現場）
  - ADMIN       → 自社現場 ID リスト
  - SUPERVISOR  → 担当現場 ID リスト
  - SUPERVISOR 担当なし → []

  【EntryRepository 管理者向けクエリ】
  - get_pending_entries: ページネーション
  - get_pending_entries: keyword 検索（氏名・受付番号）
  - get_pending_entries: site_ids スコープ（スコープ外は返さない）
  - get_entry_detail: worker + site + approval_logs を eager load
  - get_entry_detail: site_ids スコープ外は None
  - approve: pending → approved
  - reject: pending → rejected

  【ApprovalLogRepository】
  - create_log: ログが作成される
  - get_by_entry: 時系列順

  【ApprovalService】
  - list_pending: ロールスコープ適用
  - list_pending: keyword 検索
  - list_pending: site_id_filter がスコープ外 → 403
  - list_pending: SUPERVISOR 担当なし → 空リスト
  - get_detail: 正常
  - get_detail: スコープ外 → 404
  - approve: 正常 → status=approved, approval_log 作成
  - approve: pending 以外 → 409
  - approve: スコープ外 → 404
  - reject: 正常 → status=rejected, approval_log 作成
  - reject: pending 以外 → 409

  【API エンドポイント (httpx)】
  - GET /api/admin/entries/pending → 200
  - GET /api/admin/entries/{id} → 200
  - POST /api/admin/entries/{id}/approve → 200
  - POST /api/admin/entries/{id}/reject → 200
  - 認証なし → 401
  - SUPERVISOR スコープ外の現場 → 404
  - approve で status≠pending → 409
  - entry_session token で管理 API へアクセス → 401

実行方法:
    make test-approval
    docker compose exec backend pytest tests/test_approval.py -v
"""
from __future__ import annotations

import secrets
import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.core.security import create_entry_session_token
from app.core.state_machine import assert_can_transition, can_transition
from app.db.session import get_db
from app.main import app
from app.models.admin_user import AdminRole, AdminUser
from app.models.approval_log import ApprovalAction, ApprovalLog
from app.models.company import Company
from app.models.entry import EntryStatus, WorkerSiteEntry
from app.models.qr_code import SiteQrCode
from app.models.site import Site
from app.models.worker import Worker
from app.repositories.approval_log import ApprovalLogRepository
from app.repositories.entry import EntryRepository
from app.repositories.site import SiteRepository
from app.schemas.admin_entry import ApproveRequest, RejectRequest
from app.services.approval import ApprovalService


# =============================================================================
# ヘルパー・ファクトリ
# =============================================================================

def _uuid() -> str:
    return str(uuid.uuid4())


def _make_company(name: str = "テスト建設") -> Company:
    return Company(id=_uuid(), name=name, is_active=True)


def _make_site(company_id: str, *, supervisor_id: str | None = None, name: str = "テスト現場") -> Site:
    return Site(
        id=_uuid(),
        company_id=company_id,
        name=name,
        require_health_check=True,
        require_insurance=True,
        is_active=True,
        supervisor_id=supervisor_id,
    )


def _make_qr(site_id: str) -> SiteQrCode:
    return SiteQrCode(
        id=_uuid(),
        site_id=site_id,
        token=secrets.token_urlsafe(48),
        pin_required=False,
        is_active=True,
    )


def _make_worker(
    *,
    phone: str = "09011111111",
    last_name: str = "田中",
    first_name: str = "太郎",
    birth_date: date | None = date(1990, 1, 1),
    job_title: str | None = "型枠大工",
) -> Worker:
    return Worker(
        id=_uuid(),
        phone=phone,
        phone_normalized=phone,
        last_name=last_name,
        first_name=first_name,
        worker_type="company_employee",
        affiliation_company="テスト建設",
        job_title=job_title,
        birth_date=birth_date,
        is_active=True,
        consent_agreed_at=datetime.now(timezone.utc),
    )


def _make_entry(
    worker_id: str,
    site_id: str,
    qr_id: str,
    *,
    status: str = "pending",
    receipt_number: str | None = None,
    planned_entry_date: date | None = date(2026, 6, 1),
) -> WorkerSiteEntry:
    now = datetime.now(timezone.utc)
    return WorkerSiteEntry(
        id=_uuid(),
        worker_id=worker_id,
        site_id=site_id,
        qr_code_id=qr_id,
        receipt_number=receipt_number or secrets.token_hex(4).upper()[:8],
        status=status,
        has_health_check=True,
        health_check_date=date(2026, 5, 1),
        planned_entry_date=planned_entry_date,
        draft_started_at=now,
        last_saved_at=now,
        submitted_at=now if status != "draft" else None,
    )


def _make_admin(
    company_id: str,
    *,
    role: str = AdminRole.ADMIN.value,
    supervisor_id: str | None = None,  # used externally to set Site.supervisor_id
) -> AdminUser:
    return AdminUser(
        id=_uuid(),
        company_id=company_id,
        email=f"admin-{_uuid()[:8]}@example.com",
        password_hash="$2b$12$fakehash",
        name="テスト管理者",
        role=role,
        is_active=True,
    )


def _make_supervisor(company_id: str) -> AdminUser:
    return AdminUser(
        id=_uuid(),
        company_id=company_id,
        email=f"sup-{_uuid()[:8]}@example.com",
        password_hash="$2b$12$fakehash",
        name="テスト監督",
        role=AdminRole.SUPERVISOR.value,
        is_active=True,
    )


def _make_super_admin(company_id: str) -> AdminUser:
    return AdminUser(
        id=_uuid(),
        company_id=company_id,
        email=f"super-{_uuid()[:8]}@example.com",
        password_hash="$2b$12$fakehash",
        name="スーパー管理者",
        role=AdminRole.SUPER_ADMIN.value,
        is_active=True,
    )


async def _seed_base(session):
    """Company → Site → QR → Worker → pending Entry を作成して返す"""
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

    entry = _make_entry(worker.id, site.id, qr.id, status="pending")
    session.add(entry)
    await session.flush()

    return company, site, qr, worker, entry


def _make_access_token(user: AdminUser) -> str:
    return create_access_token(subject=user.id)


# =============================================================================
# 1. state_machine
# =============================================================================

class TestStateMachine:
    def test_draft_to_pending_allowed(self) -> None:
        assert can_transition("draft", "pending") is True

    def test_pending_to_approved_allowed(self) -> None:
        assert can_transition("pending", "approved") is True

    def test_pending_to_rejected_allowed(self) -> None:
        assert can_transition("pending", "rejected") is True

    def test_pending_to_withdrawn_allowed(self) -> None:
        assert can_transition("pending", "withdrawn") is True

    def test_draft_to_approved_forbidden(self) -> None:
        assert can_transition("draft", "approved") is False

    def test_draft_to_rejected_forbidden(self) -> None:
        assert can_transition("draft", "rejected") is False

    def test_approved_to_any_forbidden(self) -> None:
        assert can_transition("approved", "pending") is False
        assert can_transition("approved", "rejected") is False
        assert can_transition("approved", "draft") is False

    def test_rejected_to_any_forbidden(self) -> None:
        assert can_transition("rejected", "approved") is False
        assert can_transition("rejected", "pending") is False

    def test_withdrawn_to_any_forbidden(self) -> None:
        assert can_transition("withdrawn", "approved") is False

    def test_same_status_forbidden(self) -> None:
        assert can_transition("pending", "pending") is False
        assert can_transition("approved", "approved") is False

    def test_assert_raises_409_for_invalid(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            assert_can_transition("approved", "pending")
        assert exc_info.value.status_code == 409

    def test_assert_no_raise_for_valid(self) -> None:
        # 正常遷移は例外なし
        assert_can_transition("pending", "approved")
        assert_can_transition("pending", "rejected")


# =============================================================================
# 2. SiteRepository.get_site_ids_for_user
# =============================================================================

class TestSiteRepositoryScope:
    @pytest.mark.asyncio
    async def test_super_admin_returns_none(self, db_session) -> None:
        company = _make_company()
        db_session.add(company)
        await db_session.flush()
        user = _make_super_admin(company.id)
        db_session.add(user)
        await db_session.flush()

        repo = SiteRepository(db_session)
        result = await repo.get_site_ids_for_user(user)
        assert result is None

    @pytest.mark.asyncio
    async def test_admin_returns_own_company_sites(self, db_session) -> None:
        company = _make_company()
        other_company = _make_company("他社建設")
        db_session.add_all([company, other_company])
        await db_session.flush()

        site1 = _make_site(company.id, name="自社現場A")
        site2 = _make_site(company.id, name="自社現場B")
        other_site = _make_site(other_company.id, name="他社現場")
        db_session.add_all([site1, site2, other_site])
        await db_session.flush()

        user = _make_admin(company.id)
        db_session.add(user)
        await db_session.flush()

        repo = SiteRepository(db_session)
        result = await repo.get_site_ids_for_user(user)
        assert result is not None
        assert site1.id in result
        assert site2.id in result
        assert other_site.id not in result

    @pytest.mark.asyncio
    async def test_supervisor_returns_assigned_sites_only(self, db_session) -> None:
        company = _make_company()
        db_session.add(company)
        await db_session.flush()

        supervisor = _make_supervisor(company.id)
        db_session.add(supervisor)
        await db_session.flush()

        assigned_site = _make_site(company.id, supervisor_id=supervisor.id, name="担当現場")
        other_site = _make_site(company.id, name="他の現場")
        db_session.add_all([assigned_site, other_site])
        await db_session.flush()

        repo = SiteRepository(db_session)
        result = await repo.get_site_ids_for_user(supervisor)
        assert result is not None
        assert assigned_site.id in result
        assert other_site.id not in result

    @pytest.mark.asyncio
    async def test_supervisor_no_assignment_returns_empty(self, db_session) -> None:
        company = _make_company()
        db_session.add(company)
        await db_session.flush()

        supervisor = _make_supervisor(company.id)
        db_session.add(supervisor)
        await db_session.flush()

        repo = SiteRepository(db_session)
        result = await repo.get_site_ids_for_user(supervisor)
        assert result == []


# =============================================================================
# 3. EntryRepository 管理者向けクエリ
# =============================================================================

class TestEntryRepositoryAdmin:
    @pytest.mark.asyncio
    async def test_get_pending_entries_returns_pending_only(self, db_session) -> None:
        company, site, qr, worker, entry = await _seed_base(db_session)

        # draft も追加
        draft_entry = _make_entry(worker.id, site.id, qr.id, status="draft",
                                   receipt_number="DRAFT111")
        db_session.add(draft_entry)
        await db_session.flush()

        repo = EntryRepository(db_session)
        items, total = await repo.get_pending_entries(site_ids=None)
        ids = [e.id for e in items]
        assert entry.id in ids
        assert draft_entry.id not in ids

    @pytest.mark.asyncio
    async def test_get_pending_entries_site_scope(self, db_session) -> None:
        company = _make_company()
        db_session.add(company)
        await db_session.flush()

        site_a = _make_site(company.id, name="現場A")
        site_b = _make_site(company.id, name="現場B")
        db_session.add_all([site_a, site_b])
        await db_session.flush()

        qr_a = _make_qr(site_a.id)
        qr_b = _make_qr(site_b.id)
        db_session.add_all([qr_a, qr_b])
        await db_session.flush()

        worker = _make_worker()
        db_session.add(worker)
        await db_session.flush()

        entry_a = _make_entry(worker.id, site_a.id, qr_a.id, status="pending",
                               receipt_number="ENTRYAA1")
        entry_b = _make_entry(worker.id, site_b.id, qr_b.id, status="pending",
                               receipt_number="ENTRYBB1")
        db_session.add_all([entry_a, entry_b])
        await db_session.flush()

        repo = EntryRepository(db_session)
        # site_a のみスコープ
        items, total = await repo.get_pending_entries(site_ids=[site_a.id])
        ids = [e.id for e in items]
        assert entry_a.id in ids
        assert entry_b.id not in ids
        assert total >= 1

    @pytest.mark.asyncio
    async def test_get_pending_entries_keyword_name(self, db_session) -> None:
        company = _make_company()
        db_session.add(company)
        await db_session.flush()

        site = _make_site(company.id)
        db_session.add(site)
        await db_session.flush()

        qr = _make_qr(site.id)
        db_session.add(qr)
        await db_session.flush()

        worker_tanaka = _make_worker(last_name="田中", first_name="太郎",
                                      phone="09011111111")
        worker_suzuki = _make_worker(last_name="鈴木", first_name="花子",
                                      phone="09022222222")
        db_session.add_all([worker_tanaka, worker_suzuki])
        await db_session.flush()

        entry_t = _make_entry(worker_tanaka.id, site.id, qr.id, status="pending",
                               receipt_number="TANKA001")
        entry_s = _make_entry(worker_suzuki.id, site.id, qr.id, status="pending",
                               receipt_number="SUZUK001")
        db_session.add_all([entry_t, entry_s])
        await db_session.flush()

        repo = EntryRepository(db_session)
        items, total = await repo.get_pending_entries(site_ids=None, keyword="田中")
        ids = [e.id for e in items]
        assert entry_t.id in ids
        assert entry_s.id not in ids

    @pytest.mark.asyncio
    async def test_get_pending_entries_keyword_receipt(self, db_session) -> None:
        company, site, qr, worker, entry = await _seed_base(db_session)

        repo = EntryRepository(db_session)
        receipt = entry.receipt_number
        items, _ = await repo.get_pending_entries(site_ids=None, keyword=receipt)
        ids = [e.id for e in items]
        assert entry.id in ids

    @pytest.mark.asyncio
    async def test_get_pending_entries_pagination(self, db_session) -> None:
        company = _make_company()
        db_session.add(company)
        await db_session.flush()

        site = _make_site(company.id)
        db_session.add(site)
        await db_session.flush()

        qr = _make_qr(site.id)
        db_session.add(qr)
        await db_session.flush()

        # 3 workers, 3 pending entries
        for i in range(3):
            w = _make_worker(phone=f"0901234567{i}")
            db_session.add(w)
            await db_session.flush()
            e = _make_entry(w.id, site.id, qr.id, status="pending",
                             receipt_number=f"PAGE{i}001")
            db_session.add(e)
        await db_session.flush()

        repo = EntryRepository(db_session)
        items_p1, total = await repo.get_pending_entries(
            site_ids=None, page=1, per_page=2
        )
        assert len(items_p1) == 2
        assert total >= 3

    @pytest.mark.asyncio
    async def test_get_entry_detail_scope_enforced(self, db_session) -> None:
        """スコープ外の現場の申請は None"""
        company_a = _make_company("A社")
        company_b = _make_company("B社")
        db_session.add_all([company_a, company_b])
        await db_session.flush()

        site_a = _make_site(company_a.id)
        site_b = _make_site(company_b.id)
        db_session.add_all([site_a, site_b])
        await db_session.flush()

        qr_a = _make_qr(site_a.id)
        qr_b = _make_qr(site_b.id)
        db_session.add_all([qr_a, qr_b])
        await db_session.flush()

        worker = _make_worker()
        db_session.add(worker)
        await db_session.flush()

        entry_b = _make_entry(worker.id, site_b.id, qr_b.id, status="pending",
                               receipt_number="CROSS001")
        db_session.add(entry_b)
        await db_session.flush()

        repo = EntryRepository(db_session)
        # site_a のスコープで site_b の申請を取得しようとする
        result = await repo.get_entry_detail(entry_b.id, site_ids=[site_a.id])
        assert result is None

    @pytest.mark.asyncio
    async def test_approve_sets_status_and_approved_by(self, db_session) -> None:
        company, site, qr, worker, entry = await _seed_base(db_session)

        admin = _make_admin(company.id)
        db_session.add(admin)
        await db_session.flush()

        repo = EntryRepository(db_session)
        now = datetime.now(timezone.utc)
        updated = await repo.approve(entry, approved_by=admin.id, approved_at=now)

        assert updated.status == EntryStatus.APPROVED.value
        assert updated.approved_by == admin.id
        assert updated.approved_at is not None

    @pytest.mark.asyncio
    async def test_reject_sets_status_and_reason(self, db_session) -> None:
        company, site, qr, worker, entry = await _seed_base(db_session)

        repo = EntryRepository(db_session)
        reason = "書類不備（保険証のコピーが不鮮明）"
        updated = await repo.reject(entry, rejection_reason=reason)

        assert updated.status == EntryStatus.REJECTED.value
        assert updated.rejection_reason == reason


# =============================================================================
# 4. ApprovalLogRepository
# =============================================================================

class TestApprovalLogRepository:
    @pytest.mark.asyncio
    async def test_create_log_stored(self, db_session) -> None:
        company, site, qr, worker, entry = await _seed_base(db_session)
        admin = _make_admin(company.id)
        db_session.add(admin)
        await db_session.flush()

        repo = ApprovalLogRepository(db_session)
        now = datetime.now(timezone.utc)
        log = await repo.create_log(
            entry_id=entry.id,
            actor_id=admin.id,
            action=ApprovalAction.APPROVED.value,
            reason=None,
            request_id="test-req-001",
            created_at=now,
        )

        assert log.id is not None
        assert log.entry_id == entry.id
        assert log.actor_id == admin.id
        assert log.action == "approved"
        assert log.request_id == "test-req-001"

    @pytest.mark.asyncio
    async def test_get_by_entry_returns_in_order(self, db_session) -> None:
        company, site, qr, worker, entry = await _seed_base(db_session)
        admin = _make_admin(company.id)
        db_session.add(admin)
        await db_session.flush()

        repo = ApprovalLogRepository(db_session)
        now = datetime.now(timezone.utc)

        log1 = await repo.create_log(
            entry_id=entry.id,
            actor_id=admin.id,
            action=ApprovalAction.REJECTED.value,
            reason="書類不備",
            created_at=now,
        )
        log2 = await repo.create_log(
            entry_id=entry.id,
            actor_id=admin.id,
            action=ApprovalAction.APPROVED.value,
            reason=None,
            created_at=now,
        )

        logs = await repo.get_by_entry(entry.id)
        ids = [l.id for l in logs]
        assert log1.id in ids
        assert log2.id in ids


# =============================================================================
# 5. ApprovalService
# =============================================================================

class TestApprovalServiceListPending:
    @pytest.mark.asyncio
    async def test_super_admin_sees_all_sites(self, db_session) -> None:
        company_a = _make_company("A社")
        company_b = _make_company("B社")
        db_session.add_all([company_a, company_b])
        await db_session.flush()

        site_a = _make_site(company_a.id, name="A社現場")
        site_b = _make_site(company_b.id, name="B社現場")
        db_session.add_all([site_a, site_b])
        await db_session.flush()

        qr_a = _make_qr(site_a.id)
        qr_b = _make_qr(site_b.id)
        db_session.add_all([qr_a, qr_b])
        await db_session.flush()

        worker = _make_worker()
        db_session.add(worker)
        await db_session.flush()

        entry_a = _make_entry(worker.id, site_a.id, qr_a.id, status="pending",
                               receipt_number="SUPA0001")
        entry_b = _make_entry(worker.id, site_b.id, qr_b.id, status="pending",
                               receipt_number="SUPB0001")
        db_session.add_all([entry_a, entry_b])
        await db_session.flush()

        super_admin = _make_super_admin(company_a.id)
        db_session.add(super_admin)
        await db_session.flush()

        service = ApprovalService(db_session)
        result = await service.list_pending(super_admin)
        ids = [item.id for item in result.items]
        assert entry_a.id in ids
        assert entry_b.id in ids

    @pytest.mark.asyncio
    async def test_admin_sees_own_company_only(self, db_session) -> None:
        company_a = _make_company("A社")
        company_b = _make_company("B社")
        db_session.add_all([company_a, company_b])
        await db_session.flush()

        site_a = _make_site(company_a.id, name="A社現場")
        site_b = _make_site(company_b.id, name="B社現場")
        db_session.add_all([site_a, site_b])
        await db_session.flush()

        qr_a = _make_qr(site_a.id)
        qr_b = _make_qr(site_b.id)
        db_session.add_all([qr_a, qr_b])
        await db_session.flush()

        worker = _make_worker()
        db_session.add(worker)
        await db_session.flush()

        entry_a = _make_entry(worker.id, site_a.id, qr_a.id, status="pending",
                               receipt_number="ADMA0001")
        entry_b = _make_entry(worker.id, site_b.id, qr_b.id, status="pending",
                               receipt_number="ADMB0001")
        db_session.add_all([entry_a, entry_b])
        await db_session.flush()

        admin_a = _make_admin(company_a.id)
        db_session.add(admin_a)
        await db_session.flush()

        service = ApprovalService(db_session)
        result = await service.list_pending(admin_a)
        ids = [item.id for item in result.items]
        assert entry_a.id in ids
        assert entry_b.id not in ids

    @pytest.mark.asyncio
    async def test_supervisor_sees_assigned_only(self, db_session) -> None:
        company = _make_company()
        db_session.add(company)
        await db_session.flush()

        supervisor = _make_supervisor(company.id)
        db_session.add(supervisor)
        await db_session.flush()

        site_assigned = _make_site(company.id, supervisor_id=supervisor.id, name="担当現場")
        site_other = _make_site(company.id, name="他の現場")
        db_session.add_all([site_assigned, site_other])
        await db_session.flush()

        qr_a = _make_qr(site_assigned.id)
        qr_o = _make_qr(site_other.id)
        db_session.add_all([qr_a, qr_o])
        await db_session.flush()

        worker = _make_worker()
        db_session.add(worker)
        await db_session.flush()

        entry_a = _make_entry(worker.id, site_assigned.id, qr_a.id, status="pending",
                               receipt_number="SUPA0001")
        entry_o = _make_entry(worker.id, site_other.id, qr_o.id, status="pending",
                               receipt_number="SUPO0001")
        db_session.add_all([entry_a, entry_o])
        await db_session.flush()

        service = ApprovalService(db_session)
        result = await service.list_pending(supervisor)
        ids = [item.id for item in result.items]
        assert entry_a.id in ids
        assert entry_o.id not in ids

    @pytest.mark.asyncio
    async def test_supervisor_no_assignment_empty_list(self, db_session) -> None:
        company = _make_company()
        db_session.add(company)
        await db_session.flush()

        supervisor = _make_supervisor(company.id)
        db_session.add(supervisor)
        await db_session.flush()

        service = ApprovalService(db_session)
        result = await service.list_pending(supervisor)
        assert result.items == []
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_site_id_filter_out_of_scope_raises_403(self, db_session) -> None:
        company_a = _make_company("A社")
        company_b = _make_company("B社")
        db_session.add_all([company_a, company_b])
        await db_session.flush()

        site_b = _make_site(company_b.id, name="B社現場")
        db_session.add(site_b)
        await db_session.flush()

        admin_a = _make_admin(company_a.id)
        db_session.add(admin_a)
        await db_session.flush()

        service = ApprovalService(db_session)
        with pytest.raises(Exception) as exc_info:
            await service.list_pending(admin_a, site_id_filter=site_b.id)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_keyword_search_works(self, db_session) -> None:
        company, site, qr, worker, entry = await _seed_base(db_session)
        admin = _make_admin(company.id)
        db_session.add(admin)
        await db_session.flush()

        service = ApprovalService(db_session)
        result = await service.list_pending(admin, keyword="田中")
        ids = [item.id for item in result.items]
        assert entry.id in ids


class TestApprovalServiceApprove:
    @pytest.mark.asyncio
    async def test_approve_changes_status_and_creates_log(self, db_session) -> None:
        company, site, qr, worker, entry = await _seed_base(db_session)
        admin = _make_admin(company.id)
        db_session.add(admin)
        await db_session.flush()

        service = ApprovalService(db_session)
        result = await service.approve(
            admin,
            entry.id,
            ApproveRequest(reason="問題なし"),
        )

        assert result.status == "approved"
        assert result.approved_by == admin.id
        assert result.approved_at is not None

        # ログ確認
        log_repo = ApprovalLogRepository(db_session)
        logs = await log_repo.get_by_entry(entry.id)
        assert len(logs) == 1
        assert logs[0].action == "approved"
        assert logs[0].actor_id == admin.id
        assert logs[0].reason == "問題なし"

    @pytest.mark.asyncio
    async def test_approve_without_reason_ok(self, db_session) -> None:
        company, site, qr, worker, entry = await _seed_base(db_session)
        admin = _make_admin(company.id)
        db_session.add(admin)
        await db_session.flush()

        service = ApprovalService(db_session)
        result = await service.approve(admin, entry.id, ApproveRequest())
        assert result.status == "approved"

    @pytest.mark.asyncio
    async def test_approve_non_pending_raises_409(self, db_session) -> None:
        company = _make_company()
        db_session.add(company)
        await db_session.flush()

        site = _make_site(company.id)
        db_session.add(site)
        await db_session.flush()

        qr = _make_qr(site.id)
        db_session.add(qr)
        await db_session.flush()

        worker = _make_worker()
        db_session.add(worker)
        await db_session.flush()

        # already approved
        approved_entry = _make_entry(worker.id, site.id, qr.id, status="approved",
                                      receipt_number="APPRD001")
        db_session.add(approved_entry)
        await db_session.flush()

        admin = _make_admin(company.id)
        db_session.add(admin)
        await db_session.flush()

        service = ApprovalService(db_session)
        with pytest.raises(Exception) as exc_info:
            await service.approve(admin, approved_entry.id, ApproveRequest())
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_approve_out_of_scope_raises_404(self, db_session) -> None:
        company_a = _make_company("A社")
        company_b = _make_company("B社")
        db_session.add_all([company_a, company_b])
        await db_session.flush()

        site_b = _make_site(company_b.id, name="B社現場")
        db_session.add(site_b)
        await db_session.flush()

        qr_b = _make_qr(site_b.id)
        db_session.add(qr_b)
        await db_session.flush()

        worker = _make_worker()
        db_session.add(worker)
        await db_session.flush()

        entry_b = _make_entry(worker.id, site_b.id, qr_b.id, status="pending",
                               receipt_number="CROSS001")
        db_session.add(entry_b)
        await db_session.flush()

        admin_a = _make_admin(company_a.id)
        db_session.add(admin_a)
        await db_session.flush()

        service = ApprovalService(db_session)
        with pytest.raises(Exception) as exc_info:
            await service.approve(admin_a, entry_b.id, ApproveRequest())
        assert exc_info.value.status_code == 404


class TestApprovalServiceReject:
    @pytest.mark.asyncio
    async def test_reject_sets_status_and_reason_and_creates_log(self, db_session) -> None:
        company, site, qr, worker, entry = await _seed_base(db_session)
        admin = _make_admin(company.id)
        db_session.add(admin)
        await db_session.flush()

        reason = "保険証のコピーが不鮮明です。再提出をお願いします。"
        service = ApprovalService(db_session)
        result = await service.reject(
            admin,
            entry.id,
            RejectRequest(reason=reason),
        )

        assert result.status == "rejected"
        assert result.rejection_reason == reason

        log_repo = ApprovalLogRepository(db_session)
        logs = await log_repo.get_by_entry(entry.id)
        assert len(logs) == 1
        assert logs[0].action == "rejected"
        assert logs[0].reason == reason

    @pytest.mark.asyncio
    async def test_reject_approved_raises_409(self, db_session) -> None:
        company = _make_company()
        db_session.add(company)
        await db_session.flush()

        site = _make_site(company.id)
        db_session.add(site)
        await db_session.flush()

        qr = _make_qr(site.id)
        db_session.add(qr)
        await db_session.flush()

        worker = _make_worker()
        db_session.add(worker)
        await db_session.flush()

        approved_entry = _make_entry(worker.id, site.id, qr.id, status="approved",
                                      receipt_number="APPRD002")
        db_session.add(approved_entry)
        await db_session.flush()

        admin = _make_admin(company.id)
        db_session.add(admin)
        await db_session.flush()

        service = ApprovalService(db_session)
        with pytest.raises(Exception) as exc_info:
            await service.reject(admin, approved_entry.id, RejectRequest(reason="遅延"))
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_reject_draft_raises_409(self, db_session) -> None:
        company = _make_company()
        db_session.add(company)
        await db_session.flush()

        site = _make_site(company.id)
        db_session.add(site)
        await db_session.flush()

        qr = _make_qr(site.id)
        db_session.add(qr)
        await db_session.flush()

        worker = _make_worker()
        db_session.add(worker)
        await db_session.flush()

        draft_entry = _make_entry(worker.id, site.id, qr.id, status="draft",
                                   receipt_number="DRAFT002")
        db_session.add(draft_entry)
        await db_session.flush()

        admin = _make_admin(company.id)
        db_session.add(admin)
        await db_session.flush()

        service = ApprovalService(db_session)
        with pytest.raises(Exception) as exc_info:
            await service.reject(admin, draft_entry.id, RejectRequest(reason="理由"))
        assert exc_info.value.status_code == 409


# =============================================================================
# 6. API エンドポイント (httpx)
# =============================================================================

async def _seed_api_setup(session):
    """API テスト用: Company → Site → QR → Worker → pending Entry → ADMIN を作成"""
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

    entry = _make_entry(worker.id, site.id, qr.id, status="pending",
                         receipt_number="API10001")
    session.add(entry)
    await session.flush()

    admin = _make_admin(company.id)
    session.add(admin)
    await session.flush()

    return company, site, qr, worker, entry, admin


class TestApprovalAPI:
    @pytest.mark.asyncio
    async def test_list_pending_200(self, db_session) -> None:
        company, site, qr, worker, entry, admin = await _seed_api_setup(db_session)
        token = _make_access_token(admin)

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/api/admin/entries/pending",
                    headers={"Authorization": f"Bearer {token}"},
                )
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data
            assert "total" in data
            ids = [item["id"] for item in data["items"]]
            assert entry.id in ids
        finally:
            app.dependency_overrides.pop(get_db, None)

    @pytest.mark.asyncio
    async def test_get_entry_detail_200(self, db_session) -> None:
        company, site, qr, worker, entry, admin = await _seed_api_setup(db_session)
        token = _make_access_token(admin)

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    f"/api/admin/entries/{entry.id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["id"] == entry.id
            assert data["status"] == "pending"
            assert "worker" in data
            assert "approval_logs" in data
        finally:
            app.dependency_overrides.pop(get_db, None)

    @pytest.mark.asyncio
    async def test_approve_200(self, db_session) -> None:
        company, site, qr, worker, entry, admin = await _seed_api_setup(db_session)
        token = _make_access_token(admin)

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/api/admin/entries/{entry.id}/approve",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"reason": None},
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "approved"
            assert data["approved_by"] == admin.id
        finally:
            app.dependency_overrides.pop(get_db, None)

    @pytest.mark.asyncio
    async def test_reject_200(self, db_session) -> None:
        company, site, qr, worker, entry, admin = await _seed_api_setup(db_session)
        token = _make_access_token(admin)

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/api/admin/entries/{entry.id}/reject",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"reason": "書類が不備です"},
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "rejected"
            assert data["rejection_reason"] == "書類が不備です"
        finally:
            app.dependency_overrides.pop(get_db, None)

    @pytest.mark.asyncio
    async def test_no_auth_returns_401(self, db_session) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/admin/entries/pending")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_entry_session_token_rejected_by_admin_api(self, db_session) -> None:
        """公開セッショントークンで管理 API へアクセス → 401"""
        company = _make_company()
        db_session.add(company)
        await db_session.flush()

        site = _make_site(company.id)
        db_session.add(site)
        await db_session.flush()

        qr = _make_qr(site.id)
        db_session.add(qr)
        await db_session.flush()

        # entry_session トークン（QR 検証後に発行されるもの）
        entry_token = create_entry_session_token(
            site_id=site.id,
            qr_code_id=qr.id,
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/admin/entries/pending",
                headers={"Authorization": f"Bearer {entry_token}"},
            )
        # entry_session は access_token ではないので 401
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_approve_out_of_scope_returns_404(self, db_session) -> None:
        """ADMIN が他社現場の申請を approve しようとすると 404"""
        company_a = _make_company("A社")
        company_b = _make_company("B社")
        db_session.add_all([company_a, company_b])
        await db_session.flush()

        site_b = _make_site(company_b.id, name="B社現場")
        db_session.add(site_b)
        await db_session.flush()

        qr_b = _make_qr(site_b.id)
        db_session.add(qr_b)
        await db_session.flush()

        worker = _make_worker()
        db_session.add(worker)
        await db_session.flush()

        entry_b = _make_entry(worker.id, site_b.id, qr_b.id, status="pending",
                               receipt_number="CROSSAP1")
        db_session.add(entry_b)
        await db_session.flush()

        admin_a = _make_admin(company_a.id)
        db_session.add(admin_a)
        await db_session.flush()

        token = _make_access_token(admin_a)

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/api/admin/entries/{entry_b.id}/approve",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"reason": None},
                )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.pop(get_db, None)

    @pytest.mark.asyncio
    async def test_approve_already_approved_returns_409(self, db_session) -> None:
        company = _make_company()
        db_session.add(company)
        await db_session.flush()

        site = _make_site(company.id)
        db_session.add(site)
        await db_session.flush()

        qr = _make_qr(site.id)
        db_session.add(qr)
        await db_session.flush()

        worker = _make_worker()
        db_session.add(worker)
        await db_session.flush()

        # 既に approved な申請
        approved_entry = _make_entry(worker.id, site.id, qr.id, status="approved",
                                      receipt_number="ALRDY001")
        db_session.add(approved_entry)
        await db_session.flush()

        admin = _make_admin(company.id)
        db_session.add(admin)
        await db_session.flush()

        token = _make_access_token(admin)

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/api/admin/entries/{approved_entry.id}/approve",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"reason": None},
                )
            assert resp.status_code == 409
        finally:
            app.dependency_overrides.pop(get_db, None)

    @pytest.mark.asyncio
    async def test_reject_missing_reason_returns_422(self, db_session) -> None:
        """reason なし → 422 (Pydantic バリデーション)"""
        company, site, qr, worker, entry, admin = await _seed_api_setup(db_session)
        token = _make_access_token(admin)

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/api/admin/entries/{entry.id}/reject",
                    headers={"Authorization": f"Bearer {token}"},
                    json={},  # reason なし
                )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.pop(get_db, None)

    @pytest.mark.asyncio
    async def test_get_detail_unknown_entry_returns_404(self, db_session) -> None:
        company, site, qr, worker, entry, admin = await _seed_api_setup(db_session)
        token = _make_access_token(admin)

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    f"/api/admin/entries/{_uuid()}",
                    headers={"Authorization": f"Bearer {token}"},
                )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.pop(get_db, None)
