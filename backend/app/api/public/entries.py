"""
公開 入場申請 API（Draft ライフサイクル）

作業員（未ログイン）が入場申請フォームを操作するためのエンドポイント。

エンドポイント:
    POST /api/public/entries/draft
        draft ステータスで申請を新規作成する。
    PATCH /api/public/entries/{id}
        draft を部分更新する（autosave）。何度でも呼び出し可能。
    POST /api/public/entries/{id}/submit
        draft を submit して pending に遷移させる。

フロー:
    [QR 認証] → POST /qr/verify → entry_session_token
        → POST /entries/draft            (receipt_number 発行)
        → PATCH /entries/{id} ×N        (autosave)
        → POST /entries/{id}/submit      (必須チェック + pending 遷移)

セキュリティ:
    - 全エンドポイントで entry_session 認証必須
    - entry_session の site_id と entry.site_id を照合（draft hijack 防止）
    - submit 時に IP アドレスを SHA256 ハッシュ化して保存（平文不保持）
    - status=draft 以外への PATCH / submit は 409
"""
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.public_deps import get_current_entry_session
from app.db.session import get_db
from app.schemas.entry import (
    DraftCreateRequest,
    DraftEntryResponse,
    DraftUpdateRequest,
    SubmitResponse,
)
from app.services.draft_entry import DraftEntryService

router = APIRouter(prefix="/entries", tags=["public-entries"])


def _get_client_ip(request: Request) -> str:
    """
    クライアント IP アドレスを取得する。

    Nginx が X-Forwarded-For ヘッダーを付与するため、
    まず X-Real-IP を確認し、なければ request.client.host を使う。

    Note:
        本番では Nginx trusted proxy 設定を必ず行うこと。
        X-Forwarded-For の偽装を防ぐために nginx で設定する。
    """
    # Nginx が設定する X-Real-IP を優先
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    # フォールバック: uvicorn 直接アクセスの場合
    if request.client:
        return request.client.host
    return "unknown"


@router.post(
    "/draft",
    response_model=DraftEntryResponse,
    status_code=201,
    summary="入場申請 Draft を作成",
    description="""
draft ステータスで入場申請を新規作成します。

**既存作業員の再利用（パターン A）**:
```json
{
  "phone": "090-1234-5678",
  "worker_id": "lookup で取得した worker.id"
}
```

**新規作業員（パターン B）**:
```json
{
  "phone": "090-1234-5678",
  "last_name": "田中",
  "first_name": "太郎"
}
```

作成後は `PATCH /entries/{id}` で残りの情報を入力し、
`POST /entries/{id}/submit` で申請を確定してください。
""",
    responses={
        201: {"description": "draft 作成成功"},
        401: {"description": "entry_session が無効または期限切れ"},
        409: {"description": "この現場への有効な申請がすでに存在する"},
        422: {"description": "入力バリデーションエラー"},
    },
)
async def create_draft(
    body: DraftCreateRequest,
    db: AsyncSession = Depends(get_db),
    session_payload: dict[str, Any] = Depends(get_current_entry_session),
) -> DraftEntryResponse:
    """draft を新規作成する"""
    service = DraftEntryService(db)
    return await service.create_draft(
        body,
        site_id=session_payload["site_id"],
        qr_code_id=session_payload["qr_code_id"],
    )


@router.patch(
    "/{entry_id}",
    response_model=DraftEntryResponse,
    summary="Draft を部分更新（autosave）",
    description="""
draft の内容を部分更新します（autosave）。送信したフィールドのみ更新されます。

**フロントエンドの推奨実装**:
- 入力から 1 〜 2 秒後に自動でこのエンドポイントを呼び出す
- ネットワーク障害時はローカルストレージに一時保存し、復帰後に再送

**更新可能フィールド（作業員情報）**:
`last_name`, `first_name`, `last_name_kana`, `first_name_kana`,
`birth_date`, `gender`, `blood_type`, `emergency_contact`,
`emergency_contact_name`, `emergency_contact_relation`,
`postal_code`, `address`, `worker_type`, `affiliation_company`,
`job_title`, `experience_years`, `insurance_type`, `insurance_number`,
`consent_agreed`

**更新可能フィールド（入場情報）**:
`planned_entry_date`, `has_health_check`, `health_check_date`

> ⚠️ `status=draft` 以外の申請には更新できません（409 を返します）
""",
    responses={
        200: {"description": "autosave 成功。last_saved_at が更新される"},
        401: {"description": "entry_session が無効または期限切れ"},
        404: {"description": "申請が見つからない（または他現場の申請）"},
        409: {"description": "draft ステータスでない（すでに送信済み）"},
        422: {"description": "入力バリデーションエラー"},
    },
)
async def update_draft(
    entry_id: str,
    body: DraftUpdateRequest,
    db: AsyncSession = Depends(get_db),
    session_payload: dict[str, Any] = Depends(get_current_entry_session),
) -> DraftEntryResponse:
    """draft を部分更新する（autosave）"""
    service = DraftEntryService(db)
    return await service.update_draft(
        entry_id=entry_id,
        site_id=session_payload["site_id"],
        req=body,
    )


@router.post(
    "/{entry_id}/submit",
    response_model=SubmitResponse,
    summary="Draft を申請確定（pending に遷移）",
    description="""
draft を申請確定します。`status` が `pending` に変わります。

**submit 前の必須チェック**（不足があれば 422）:
- `last_name`, `first_name`（姓名）
- `birth_date`（生年月日）
- `job_title`（職種）
- `worker_type`（区分）
- `consent_agreed`（個人情報同意）
- 現場設定で `require_health_check=true` の場合: `has_health_check=true`
- 現場設定で `require_insurance=true` の場合: `insurance_type`, `insurance_number`

submit 後は変更できません。
""",
    responses={
        200: {"description": "申請確定。receipt_number を必ず記録してください"},
        401: {"description": "entry_session が無効または期限切れ"},
        404: {"description": "申請が見つからない（または他現場の申請）"},
        409: {"description": "draft ステータスでない（すでに送信済み）"},
        422: {"description": "必須フィールドが未入力"},
    },
)
async def submit_entry(
    entry_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_payload: dict[str, Any] = Depends(get_current_entry_session),
) -> SubmitResponse:
    """draft を申請確定して pending に遷移させる"""
    service = DraftEntryService(db)
    return await service.submit(
        entry_id=entry_id,
        site_id=session_payload["site_id"],
        client_ip=_get_client_ip(request),
    )
