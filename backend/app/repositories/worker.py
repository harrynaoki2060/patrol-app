"""
Worker Repository

作業員の検索・作成・更新を提供する。

設計方針:
  - 電話番号の正規化は呼び出し元（サービス層）で行う
  - 個人情報を含むため、返却するフィールドは常にモデル全体
    （フィルタリングはスキーマ層で行う）
  - inactive な作業員を返す get_* はメソッド名で明示する
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.worker import Worker
from app.repositories.base import BaseRepository


class WorkerRepository(BaseRepository[Worker]):
    model = Worker

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    # -------------------------------------------------------------------------
    # 検索
    # -------------------------------------------------------------------------

    async def get_by_phone_normalized(self, phone_normalized: str) -> Worker | None:
        """正規化済み電話番号で作業員を取得（active/inactive 問わず）"""
        result = await self.session.execute(
            select(Worker).where(Worker.phone_normalized == phone_normalized)
        )
        return result.scalar_one_or_none()

    async def get_active_by_phone(self, phone_normalized: str) -> Worker | None:
        """正規化済み電話番号でアクティブな作業員を取得"""
        result = await self.session.execute(
            select(Worker).where(
                Worker.phone_normalized == phone_normalized,
                Worker.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_active_by_phone_and_birth(
        self,
        phone_normalized: str,
        birth_month: int,
        birth_day: int,
    ) -> Worker | None:
        """
        正規化済み電話番号 + 生年月日の月日でアクティブな作業員を取得。

        超短縮再入場フロー（quick-match）用。
        birth_date が NULL の作業員は照合不可として None を返す。

        セキュリティ:
          - is_active チェック必須
          - 電話番号 + 月日の両方が一致する場合のみ返す
        """
        from sqlalchemy import extract
        result = await self.session.execute(
            select(Worker).where(
                Worker.phone_normalized == phone_normalized,
                Worker.is_active.is_(True),
                Worker.birth_date.is_not(None),
                extract("month", Worker.birth_date) == birth_month,
                extract("day", Worker.birth_date) == birth_day,
            )
        )
        return result.scalar_one_or_none()

    # -------------------------------------------------------------------------
    # 作成
    # -------------------------------------------------------------------------

    async def create_worker(
        self,
        *,
        phone: str,
        phone_normalized: str,
        last_name: str,
        first_name: str,
        worker_type: str = "company_employee",
        **optional_fields: object,
    ) -> Worker:
        """
        新規作業員を作成する。

        必須: phone / phone_normalized / last_name / first_name / worker_type
        任意: birth_date / job_title / gender / kana / emergency_contact 等

        注意: flush のみ実行。commit は呼び出し元（サービス層）が行う。
        """
        worker = Worker(
            phone=phone,
            phone_normalized=phone_normalized,
            last_name=last_name,
            first_name=first_name,
            worker_type=worker_type,
            **optional_fields,
        )
        self.session.add(worker)
        await self.session.flush()
        await self.session.refresh(worker)
        return worker

    # -------------------------------------------------------------------------
    # 更新
    # -------------------------------------------------------------------------

    async def update_worker(
        self,
        worker: Worker,
        updates: dict[str, object],
        updated_at: datetime,
    ) -> Worker:
        """
        作業員情報を部分更新する。

        updates: 更新するフィールド名 → 値 のマッピング（None 含む）
        updated_at: last_updated_at に設定する日時

        注意: flush のみ実行。commit は呼び出し元が行う。
        """
        for field, value in updates.items():
            setattr(worker, field, value)
        worker.last_updated_at = updated_at
        await self.session.flush()
        return worker

    async def set_consent_agreed(
        self, worker: Worker, agreed_at: datetime
    ) -> Worker:
        """個人情報同意日時を設定する"""
        worker.consent_agreed_at = agreed_at
        await self.session.flush()
        return worker
