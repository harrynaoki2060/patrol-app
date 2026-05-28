"""
受付番号生成ユーティリティ

設計方針:
  - 8 桁の大文字英数字（見間違いを起こしやすい I/O/0/1 を除外）
  - 使用文字: ABCDEFGHJKLMNPQRSTUVWXYZ23456789 (32 文字)
  - 総パターン数: 32^8 = 約 1 兆通り（実用上は衝突ゼロ）
  - DB の UNIQUE 制約により重複は防止される
  - 衝突時リトライ: 最大 MAX_RETRIES 回試みる
  - secrets モジュールを使用（暗号学的に安全な乱数）

使い方:
    from app.core.receipt import generate_receipt_number

    async def create_entry(session: AsyncSession) -> str:
        receipt = await generate_receipt_number(session)
        # → 例: "A3F7KM2P"
"""
from __future__ import annotations

import secrets
import string
from typing import TYPE_CHECKING

from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# 見間違えやすい文字を除外したアルファベット + 数字
_CHARSET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # I, O, 0, 1 を除外
_LENGTH = 8
_MAX_RETRIES = 10


def _generate_candidate() -> str:
    """ランダムな受付番号候補を 1 つ生成する"""
    return "".join(secrets.choice(_CHARSET) for _ in range(_LENGTH))


async def generate_receipt_number(session: "AsyncSession") -> str:
    """
    DB 重複なしの受付番号を生成して返す。

    処理:
      1. ランダムな 8 文字を生成
      2. DB に同じ receipt_number が存在しないか確認
      3. 衝突すれば再試行（最大 MAX_RETRIES 回）

    Args:
        session: 現在の AsyncSession（トランザクション中）

    Returns:
        DB 上でユニークな 8 文字の受付番号

    Raises:
        RuntimeError: MAX_RETRIES 回試みても衝突が解消しない場合
                      （実用上は発生しないが安全のため用意）
    """
    # 遅延 import で循環依存を回避
    from app.models.entry import WorkerSiteEntry

    for attempt in range(1, _MAX_RETRIES + 1):
        candidate = _generate_candidate()
        result = await session.execute(
            select(WorkerSiteEntry.id).where(
                WorkerSiteEntry.receipt_number == candidate
            )
        )
        if result.scalar_one_or_none() is None:
            return candidate

    # 実用上は到達しないが、安全のためエラーを投げる
    raise RuntimeError(
        f"受付番号の生成に {_MAX_RETRIES} 回失敗しました。"
        "DB の受付番号が枯渇している可能性があります"
    )
