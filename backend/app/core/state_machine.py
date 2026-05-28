"""
入場申請ステータス遷移ステートマシン

許可される遷移のみを定義し、不正な遷移は 409 Conflict で拒否する。

遷移図:
  draft  ─→ pending   （submit: 作業員が申請を確定）
  pending ─→ approved  （approve: 管理者が承認）
  pending ─→ rejected  （reject:  管理者が差戻し）
  pending ─→ withdrawn （withdraw: 取下げ）

セキュリティ方針:
  - pending 以外からの approved/rejected 遷移は禁止
  - 同一ステータスへの遷移も禁止（冪等でない操作の誤検知を防ぐ）
  - サービス層は assert_can_transition() を必ず呼ぶこと

将来の拡張:
  - rejected → draft（再申請）は別の「新規 draft 作成」フローで対応する
    （同一 entry_id を再利用せず、新規 WorkerSiteEntry を作成する）
"""
from __future__ import annotations

from fastapi import HTTPException, status

from app.models.entry import EntryStatus


# =============================================================================
# 許可される遷移マップ
# =============================================================================

# key: 現在のステータス → value: 遷移可能なステータスのセット
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    EntryStatus.DRAFT.value: {
        EntryStatus.PENDING.value,
    },
    EntryStatus.PENDING.value: {
        EntryStatus.APPROVED.value,
        EntryStatus.REJECTED.value,
        EntryStatus.WITHDRAWN.value,
    },
    # approved / rejected / withdrawn は終端状態（遷移不可）
    EntryStatus.APPROVED.value:  set(),
    EntryStatus.REJECTED.value:  set(),
    EntryStatus.WITHDRAWN.value: set(),
}


# =============================================================================
# 遷移検証
# =============================================================================

def can_transition(current: str, next_status: str) -> bool:
    """遷移が許可されているか bool で返す"""
    return next_status in ALLOWED_TRANSITIONS.get(current, set())


def assert_can_transition(current: str, next_status: str) -> None:
    """
    遷移が許可されていない場合に 409 Conflict を送出する。

    Args:
        current:     現在のステータス（EntryStatus の value）
        next_status: 遷移先ステータス（EntryStatus の value）

    Raises:
        HTTPException(409): 遷移が不正な場合
    """
    if not can_transition(current, next_status):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"ステータス '{current}' から '{next_status}' への遷移はできません。"
            ),
        )
