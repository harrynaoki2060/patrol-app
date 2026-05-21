"""
公開 作業員検索 API

QR 認証後に作業員が電話番号で既存登録を確認するエンドポイント。

エンドポイント:
    POST /api/public/workers/lookup
        電話番号で既存作業員を検索し、最小情報を返す。

セキュリティ:
    - entry_session 認証必須（QR 認証を通過した端末のみ使用可能）
    - レスポンスは WorkerSummary（個人情報最小化）
    - inactive 作業員は存在しないとして扱う
"""
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.public_deps import get_current_entry_session
from app.db.session import get_db
from app.schemas.worker import (
    QuickMatchRequest,
    QuickMatchResponse,
    WorkerLookupRequest,
    WorkerLookupResponse,
)
from app.services.worker_lookup import WorkerLookupService
from app.services.worker_quickmatch import WorkerQuickMatchService

router = APIRouter(prefix="/workers", tags=["public-workers"])


@router.post(
    "/lookup",
    response_model=WorkerLookupResponse,
    summary="電話番号で作業員を検索",
    description="""
電話番号に紐づく既存作業員を検索します。

- 見つかった場合: `exists=true` + 氏名・所属・職種の概要を返します
- 見つからない場合: `exists=false`（新規登録が必要）
- **inactive な作業員は `exists=false` として扱います**

フロントエンドは `exists=true` の場合に「前回の登録情報を使用しますか？」
を表示し、ユーザーが同意したら `worker.id` を使って Draft Create を行います。

> ⚠️ このエンドポイントは entry_session 認証が必要です。
> QR 認証（POST /api/public/qr/verify）を先に実行してください。
""",
    responses={
        200: {"description": "検索成功（見つからない場合も 200 で exists=false）"},
        401: {"description": "entry_session が無効または期限切れ"},
        422: {"description": "電話番号の形式が不正"},
    },
)
async def lookup_worker(
    body: WorkerLookupRequest,
    db: AsyncSession = Depends(get_db),
    _session: dict[str, Any] = Depends(get_current_entry_session),
) -> WorkerLookupResponse:
    """
    電話番号で作業員を検索する。

    entry_session の site_id は lookup では使用しない
    （作業員は複数現場に所属できるため）。
    """
    service = WorkerLookupService(db)
    return await service.lookup(body.phone)


@router.post(
    "/quick-match",
    response_model=QuickMatchResponse,
    summary="電話番号 + 生年月日(月日)で既存作業員を照合",
    description="""
既存作業員を「電話番号 + 生年月日(月日のみ)」で照合します。
**目標: 入力から照合まで 30 秒以内**

- 照合成功: `matched=true` + 氏名・所属の概要（確認画面用）
- 照合失敗: `matched=false`（通常フォームへ）

**セキュリティ**:
- 電話番号のみ / 月日のみの部分一致では `matched=true` を返しません
- inactive 作業員は `matched=false`（存在リーク防止）
- レスポンスで電話番号・生年月日は返しません

> ⚠️ このエンドポイントは entry_session 認証が必要です。
""",
    responses={
        200: {"description": "照合結果（見つからない場合も 200 で matched=false）"},
        401: {"description": "entry_session が無効または期限切れ"},
        422: {"description": "入力バリデーションエラー"},
    },
)
async def quick_match_worker(
    body: QuickMatchRequest,
    db: AsyncSession = Depends(get_db),
    _session: dict[str, Any] = Depends(get_current_entry_session),
) -> QuickMatchResponse:
    """
    電話番号 + 生年月日(月日)で既存作業員を照合する。

    超短縮再入場フロー用エンドポイント。
    通常の lookup（電話番号のみ）より強い認証（月日照合）を行うため、
    返却する WorkerSummary は lookup と同じ最小情報に限定する。
    """
    service = WorkerQuickMatchService(db)
    return await service.quick_match(
        phone_raw=body.phone,
        birth_month=body.birth_month,
        birth_day=body.birth_day,
    )
