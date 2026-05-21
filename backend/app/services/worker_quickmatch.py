"""
作業員 クイックマッチ サービス

既存作業員を「電話番号 + 生年月日(月日)」で照合し、
30秒以内の超短縮再入場フローを実現する。

セキュリティ設計:
  - 電話番号のみ / 月日のみの部分一致では matched=True を返さない
  - inactive 作業員は matched=False として返す（存在リーク防止）
  - 電話番号が存在するか否かを matched=False と区別しない
  - ログは worker_id のみ記録し、電話番号の先頭4桁のみをマスクして記録
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.validators import normalize_phone
from app.models.worker import Worker
from app.repositories.worker import WorkerRepository
from app.schemas.worker import QuickMatchResponse, WorkerSummary

logger = logging.getLogger(__name__)


class WorkerQuickMatchService:
    """クイックマッチサービス"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = WorkerRepository(session)

    async def quick_match(
        self,
        phone_raw: str,
        birth_month: int,
        birth_day: int,
    ) -> QuickMatchResponse:
        """
        電話番号 + 生年月日(月日)で作業員を照合する。

        処理:
          1. 電話番号を正規化
          2. phone_normalized + birth_month + birth_day が全一致するアクティブ作業員を検索
          3. 見つかれば matched=True + WorkerSummary を返す
          4. 見つからなければ matched=False（新規入力が必要）

        Note:
          birth_date が NULL の作業員は照合不可 → matched=False。
          これはセキュリティ上の意図的な動作（不完全なデータで認証を通さない）。
        """
        phone_normalized = normalize_phone(phone_raw)
        worker = await self.repo.get_active_by_phone_and_birth(
            phone_normalized,
            birth_month=birth_month,
            birth_day=birth_day,
        )

        if worker is None:
            logger.info(
                "QuickMatch: not matched phone_normalized=%.4s... month=%d day=%d",
                phone_normalized, birth_month, birth_day,
            )
            return QuickMatchResponse(matched=False, worker=None)

        logger.info(
            "QuickMatch: matched worker_id=%s", worker.id
        )
        return QuickMatchResponse(
            matched=True,
            worker=_to_summary(worker),
        )


def _to_summary(worker: Worker) -> WorkerSummary:
    """Worker モデルから WorkerSummary を生成する（個人情報フィルタリング）"""
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
