"""
作業員検索サービス

QR 認証後のフォーム開始時に呼び出される。
電話番号で既存作業員を検索し、最小限の情報を返す。

セキュリティ設計:
  - inactive な作業員は exists=False として返す（存在リーク防止）
  - 返却する情報は WorkerSummary に限定（個人情報最小化）
  - 他現場の入場情報は一切返さない
  - lookup だけでは何も変更しない（read-only）
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.validators import normalize_phone
from app.models.worker import Worker
from app.repositories.worker import WorkerRepository
from app.schemas.worker import WorkerLookupResponse, WorkerSummary

logger = logging.getLogger(__name__)


class WorkerLookupService:
    """作業員検索サービス"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = WorkerRepository(session)

    async def lookup(self, phone_raw: str) -> WorkerLookupResponse:
        """
        電話番号で作業員を検索する。

        処理:
          1. 電話番号を正規化（すでにスキーマ層で正規化済みだが防衛的に再処理）
          2. active な作業員を検索
          3. 見つかれば WorkerSummary（最小情報）を返す
          4. 見つからなければ / inactive なら exists=False を返す

        Note:
          inactive 作業員を「存在する」と返すとプライバシー問題になるため、
          必ず is_active=True のものだけを返す。
        """
        phone_normalized = normalize_phone(phone_raw)
        worker = await self.repo.get_active_by_phone(phone_normalized)

        if worker is None:
            logger.info(
                "Worker lookup: not found phone_normalized=%.4s...", phone_normalized
            )
            return WorkerLookupResponse(exists=False, worker=None)

        logger.info(
            "Worker lookup: found worker_id=%s", worker.id
        )
        return WorkerLookupResponse(
            exists=True,
            worker=_to_summary(worker),
        )


def _to_summary(worker: Worker) -> WorkerSummary:
    """
    Worker モデルから WorkerSummary を生成する（個人情報フィルタリング）。

    含めない情報:
      - phone / phone_normalized（作業員自身が知っているため不要）
      - birth_date（センシティブ）
      - address / postal_code（センシティブ）
      - emergency_contact（センシティブ）
      - insurance_type / insurance_number（センシティブ）
      - consent_agreed_at（内部管理情報）
    """
    return WorkerSummary(
        id=worker.id,
        last_name=worker.last_name,
        first_name=worker.first_name,
        last_name_kana=worker.last_name_kana,
        first_name_kana=worker.first_name_kana,
        worker_type=worker.worker_type,
        affiliation_company=worker.affiliation_company,
        job_title=worker.job_title,
    )
