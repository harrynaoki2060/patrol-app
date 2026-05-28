"""
公開 API 用 FastAPI 依存性注入

entry_session トークン（type="entry_session"）の検証を担う。
管理 API の deps.py とは完全に分離し、相互流用を不可能にする。

設計ポイント:
  - decode_entry_session_token() は type != "entry_session" で None を返すため
    管理 API 用の access token を使っても 401 になる（逆方向も同様）
  - payload には sub（user_id）が存在しない。site_id / qr_code_id のみ。
  - DB 問い合わせなし（JWT の署名・有効期限のみ検証）

使い方:
    from app.api.public_deps import get_current_entry_session

    @router.post("/entries")
    async def submit_entry(
        payload = Depends(get_current_entry_session),
        ...
    ):
        site_id = payload["site_id"]
        qr_code_id = payload["qr_code_id"]
        ...
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_entry_session_token

# Bearer スキーム（Swagger UI で🔒アイコンが表示される）
_bearer_scheme = HTTPBearer(auto_error=True)

# 401 統一エラー
_ENTRY_SESSION_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="セッションが無効または期限切れです。QRコードを再度読み込んでください",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_entry_session(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict[str, Any]:
    """
    Authorization: Bearer <entry_session_token> を検証して payload を返す。

    Returns:
        dict with keys: type, site_id, qr_code_id, iat, exp, jti

    Raises:
        HTTPException 401: トークンが無効 / 期限切れ / type != "entry_session"
    """
    payload = decode_entry_session_token(credentials.credentials)
    if payload is None:
        raise _ENTRY_SESSION_ERROR

    # 必須フィールドの存在チェック（改ざん・不正生成トークン対策）
    if not payload.get("site_id") or not payload.get("qr_code_id"):
        raise _ENTRY_SESSION_ERROR

    return payload
