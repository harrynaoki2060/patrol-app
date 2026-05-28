"""
Draft 入場申請サービス

draft の作成・更新（autosave）・submit を担う。

セキュリティ設計:
  - entry_session の site_id と entry.site_id を常に照合（draft hijack 防止）
  - status=draft のみ更新可能（状態遷移の厳格化）
  - submit 時に必須フィールドを検証（現場設定に応じて動的に変更）
  - IP アドレスは SHA256 ハッシュのみ保存（平文不保持）
  - 重複有効申請（draft/pending/approved）を拒否（DB 部分インデックスと二重防護）

コミット戦略:
  - 各メソッドは最後に 1 回 commit する（中間 flush のみで途中コミットしない）
  - 例外時はトランザクション全体がロールバックされる
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.receipt import generate_receipt_number
from app.core.validators import (
    get_age_warning,
    get_health_check_warning,
    normalize_phone,
)
from app.models.entry import EntryStatus, WorkerSiteEntry
from app.models.worker import Worker
from app.repositories.entry import EntryRepository
from app.repositories.worker import WorkerRepository
from app.repositories.site import SiteRepository
from app.schemas.entry import (
    DraftCreateRequest,
    DraftEntryResponse,
    DraftUpdateRequest,
    SubmitResponse,
    WorkerInEntry,
)

logger = logging.getLogger(__name__)

# =============================================================================
# エラー定数
# =============================================================================

def _not_found_or_forbidden() -> HTTPException:
    """entry が見つからない / site_id 不一致（区別しない）"""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="申請が見つかりません",
    )


_NOT_DRAFT_ERROR = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail="この申請はすでに送信済みのため変更できません",
)

_DUPLICATE_ERROR = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail="この現場への有効な入場申請がすでに存在します",
)

_WORKER_MISMATCH_ERROR = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="電話番号と作業員 ID が一致しません",
)

_WORKER_NOT_FOUND_ERROR = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="指定された作業員が見つかりません",
)


# =============================================================================
# サービス
# =============================================================================

class DraftEntryService:
    """Draft 入場申請サービス。各リクエストでインスタンスを生成する。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.worker_repo = WorkerRepository(session)
        self.entry_repo = EntryRepository(session)
        self.site_repo = SiteRepository(session)

    # -------------------------------------------------------------------------
    # Draft 作成
    # -------------------------------------------------------------------------

    async def create_draft(
        self,
        req: DraftCreateRequest,
        site_id: str,
        qr_code_id: str,
    ) -> DraftEntryResponse:
        """
        draft ステータスの入場申請を作成する。

        処理順:
          1. 作業員の特定（既存 or 新規作成）
          2. 重複有効申請チェック
          3. 受付番号生成
          4. draft 作成
          5. commit
          6. レスポンス生成

        Args:
            req: DraftCreateRequest（phone は正規化済み）
            site_id: entry_session から取得した現場 ID
            qr_code_id: entry_session から取得した QR コード ID
        """
        now = datetime.now(timezone.utc)
        phone_normalized = req.phone  # スキーマ層で正規化済み

        # 1. 作業員の特定
        worker = await self._resolve_worker(req, phone_normalized, now)

        # 2. 重複有効申請チェック
        existing = await self.entry_repo.get_active_by_worker_and_site(
            worker.id, site_id
        )
        if existing is not None:
            logger.warning(
                "Duplicate entry attempt: worker_id=%s site_id=%s existing_id=%s",
                worker.id,
                site_id,
                existing.id,
            )
            raise _DUPLICATE_ERROR

        # 3. 受付番号生成（DB 照合で重複チェック）
        receipt_number = await generate_receipt_number(self.session)

        # 4. draft 作成
        entry = await self.entry_repo.create_draft(
            worker_id=worker.id,
            site_id=site_id,
            qr_code_id=qr_code_id,
            receipt_number=receipt_number,
            now=now,
        )

        # 5. commit
        await self.session.commit()

        logger.info(
            "Draft created: entry_id=%s receipt=%s worker_id=%s site_id=%s",
            entry.id,
            receipt_number,
            worker.id,
            site_id,
        )

        # 6. レスポンス生成（worker をリフレッシュして最新状態を取得）
        await self.session.refresh(worker)
        return _to_draft_response(entry, worker, warnings=[])

    async def _resolve_worker(
        self,
        req: DraftCreateRequest,
        phone_normalized: str,
        now: datetime,
    ) -> Worker:
        """
        作業員を特定する（既存再利用 or 新規作成）。

        パターン A: worker_id あり → 既存作業員を取得し phone 一致確認
        パターン B: worker_id なし → phone で検索。見つかれば再利用、
                    なければ新規作成
        """
        if req.worker_id is not None:
            # パターン A: 既存作業員の再利用
            worker = await self.worker_repo.get_by_id(req.worker_id)
            if worker is None or not worker.is_active:
                raise _WORKER_NOT_FOUND_ERROR
            if worker.phone_normalized != phone_normalized:
                logger.warning(
                    "Worker phone mismatch: worker_id=%s", req.worker_id
                )
                raise _WORKER_MISMATCH_ERROR
            return worker

        # パターン B: phone で検索 → なければ新規作成
        worker = await self.worker_repo.get_active_by_phone(phone_normalized)
        if worker is not None:
            logger.info("Worker reuse: worker_id=%s", worker.id)
            return worker

        # 新規作業員を作成（draft-first: 必須フィールドは後から PATCH で入力）
        worker = await self.worker_repo.create_worker(
            phone=req.phone,
            phone_normalized=phone_normalized,
            last_name=req.last_name,   # type: ignore[arg-type]  # schema validator 保証
            first_name=req.first_name,  # type: ignore[arg-type]
            worker_type="company_employee",  # PATCH で変更可能
        )
        logger.info("Worker created: worker_id=%s", worker.id)
        return worker

    # -------------------------------------------------------------------------
    # Draft 更新（autosave）
    # -------------------------------------------------------------------------

    async def update_draft(
        self,
        entry_id: str,
        site_id: str,
        req: DraftUpdateRequest,
    ) -> DraftEntryResponse:
        """
        draft を部分更新する（autosave）。

        処理順:
          1. entry 取得（site_id 照合でクロスサイト防止）
          2. status=draft であることを確認
          3. worker フィールドの更新
          4. entry フィールドの更新
          5. consent 同意処理
          6. commit
          7. 警告生成 + レスポンス返却
        """
        now = datetime.now(timezone.utc)

        # 1. entry 取得
        entry = await self.entry_repo.get_draft_by_id_and_site(entry_id, site_id)
        if entry is None:
            raise _not_found_or_forbidden()

        # 2. status チェック
        if entry.status != EntryStatus.DRAFT.value:
            raise _NOT_DRAFT_ERROR

        worker = entry.worker

        # 3. worker フィールドを更新（送信されたフィールドのみ）
        worker_fields = _extract_worker_fields(req)
        if worker_fields:
            await self.worker_repo.update_worker(worker, worker_fields, now)

        # 4. consent 処理
        if req.consent_agreed is True and worker.consent_agreed_at is None:
            await self.worker_repo.set_consent_agreed(worker, now)
            logger.info("Consent agreed: worker_id=%s", worker.id)

        # 5. entry フィールドを更新（送信されたフィールドのみ）
        entry_fields = _extract_entry_fields(req)
        await self.entry_repo.update_entry_fields(entry, entry_fields, now)

        # 6. commit
        await self.session.commit()

        # 7. 警告生成
        warnings = _build_warnings(worker)
        logger.debug(
            "Draft autosaved: entry_id=%s worker_id=%s", entry.id, worker.id
        )

        return _to_draft_response(entry, worker, warnings=warnings)

    # -------------------------------------------------------------------------
    # Submit（draft → pending）
    # -------------------------------------------------------------------------

    async def submit(
        self,
        entry_id: str,
        site_id: str,
        client_ip: str,
    ) -> SubmitResponse:
        """
        draft を submit して pending に遷移させる。

        処理順:
          1. entry 取得（site_id 照合）
          2. status=draft であることを確認
          3. 現場設定を取得（必須フィールドチェックに使用）
          4. 必須フィールド検証
          5. IP ハッシュ生成
          6. submit（status → pending）
          7. worker の consent_agreed_at が未設定なら警告ログ
          8. commit
          9. レスポンス返却
        """
        now = datetime.now(timezone.utc)

        # 1. entry 取得
        entry = await self.entry_repo.get_draft_by_id_and_site(entry_id, site_id)
        if entry is None:
            raise _not_found_or_forbidden()

        # 2. status チェック
        if entry.status != EntryStatus.DRAFT.value:
            raise _NOT_DRAFT_ERROR

        worker = entry.worker

        # 3. 現場設定取得
        site = await self.site_repo.get_by_id(site_id)
        if site is None or not site.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="現場が見つかりません",
            )

        # 4. 必須フィールド検証
        errors = _validate_for_submit(worker, entry, site)
        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "必須項目が入力されていません",
                    "fields": errors,
                },
            )

        # 5. IP ハッシュ（平文を保存しない）
        ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()

        # 6. submit
        await self.entry_repo.submit(entry, now, ip_hash)

        # 7. consent 未設定の場合は警告ログ（submit 自体は許可）
        if worker.consent_agreed_at is None:
            logger.warning(
                "Submit without consent: entry_id=%s worker_id=%s",
                entry.id,
                worker.id,
            )

        # 8. commit
        await self.session.commit()

        logger.info(
            "Entry submitted: entry_id=%s receipt=%s site_id=%s",
            entry.id,
            entry.receipt_number,
            site_id,
        )

        return SubmitResponse(
            id=entry.id,
            receipt_number=entry.receipt_number,
            status=entry.status,
            submitted_at=entry.submitted_at,  # type: ignore[arg-type]
            site_name=site.name,
        )


# =============================================================================
# Private helpers
# =============================================================================

# Worker モデルで更新可能なフィールド一覧
_WORKER_UPDATABLE_FIELDS = {
    "last_name",
    "first_name",
    "last_name_kana",
    "first_name_kana",
    "birth_date",
    "gender",
    "blood_type",
    "emergency_contact",
    "emergency_contact_name",
    "emergency_contact_relation",
    "postal_code",
    "address",
    "worker_type",
    "affiliation_company",
    "job_title",
    "experience_years",
    "insurance_type",
    "insurance_number",
}

# Entry モデルで更新可能なフィールド一覧
_ENTRY_UPDATABLE_FIELDS = {
    "planned_entry_date",
    "has_health_check",
    "health_check_date",
}


def _extract_worker_fields(req: DraftUpdateRequest) -> dict[str, Any]:
    """DraftUpdateRequest から Worker 更新フィールドのみを抽出する"""
    sent = req.model_fields_set  # Pydantic v2: 実際に送信されたフィールド名のセット
    result = {}
    for field in _WORKER_UPDATABLE_FIELDS:
        if field in sent:
            result[field] = getattr(req, field)
    return result


def _extract_entry_fields(req: DraftUpdateRequest) -> dict[str, Any]:
    """DraftUpdateRequest から Entry 更新フィールドのみを抽出する"""
    sent = req.model_fields_set
    result = {}
    for field in _ENTRY_UPDATABLE_FIELDS:
        if field in sent:
            result[field] = getattr(req, field)
    return result


def _build_warnings(worker: Worker) -> list[str]:
    """作業員情報から警告メッセージリストを生成する"""
    warnings: list[str] = []
    if worker.birth_date is not None:
        w = get_age_warning(worker.birth_date)
        if w:
            warnings.append(w)
    return warnings


def _validate_for_submit(worker: Worker, entry: WorkerSiteEntry, site: Any) -> list[str]:
    """
    submit に必要な必須フィールドが揃っているか検証する。

    Returns:
        エラーがあればフィールド名のリスト、なければ空リスト
    """
    errors: list[str] = []

    # 作業員の必須フィールド
    if not worker.last_name:
        errors.append("last_name")
    if not worker.first_name:
        errors.append("first_name")
    if worker.birth_date is None:
        errors.append("birth_date")
    if not worker.job_title:
        errors.append("job_title")
    if not worker.worker_type:
        errors.append("worker_type")

    # 現場設定に応じた必須チェック
    if site.require_health_check and not entry.has_health_check:
        errors.append("has_health_check")

    if site.require_insurance and not worker.insurance_type:
        errors.append("insurance_type")
    if site.require_insurance and not worker.insurance_number:
        errors.append("insurance_number")

    # 同意チェック（警告ではなくエラーにする）
    if worker.consent_agreed_at is None:
        errors.append("consent_agreed")

    return errors


def _to_draft_response(
    entry: WorkerSiteEntry,
    worker: Worker,
    *,
    warnings: list[str],
) -> DraftEntryResponse:
    """WorkerSiteEntry + Worker → DraftEntryResponse への変換"""
    return DraftEntryResponse(
        id=entry.id,
        receipt_number=entry.receipt_number,
        status=entry.status,
        site_id=entry.site_id,
        qr_code_id=entry.qr_code_id,
        planned_entry_date=entry.planned_entry_date,
        has_health_check=entry.has_health_check,
        health_check_date=entry.health_check_date,
        draft_started_at=entry.draft_started_at,
        last_saved_at=entry.last_saved_at,
        worker=WorkerInEntry(
            id=worker.id,
            last_name=worker.last_name,
            first_name=worker.first_name,
            last_name_kana=worker.last_name_kana,
            first_name_kana=worker.first_name_kana,
            birth_date=worker.birth_date,
            gender=worker.gender,
            blood_type=worker.blood_type,
            emergency_contact=worker.emergency_contact,
            emergency_contact_name=worker.emergency_contact_name,
            emergency_contact_relation=worker.emergency_contact_relation,
            postal_code=worker.postal_code,
            address=worker.address,
            worker_type=worker.worker_type,
            affiliation_company=worker.affiliation_company,
            job_title=worker.job_title,
            experience_years=worker.experience_years,
            insurance_type=worker.insurance_type,
            insurance_number=worker.insurance_number,
            consent_agreed_at=worker.consent_agreed_at,
        ),
        warnings=warnings,
    )
