"""
公開 QR 認証 API

QR コード URL を読み込んだ作業員（未ログイン）向けのエンドポイント。
認証なし（または entry_session 認証）でアクセスできる。

エンドポイント:
    POST /api/public/qr/verify
        QR トークン + PIN を検証して entry_session_token を発行する。
        成功すると 30 分有効なセッショントークンが返る。

セキュリティ設計:
    - レート制限は Nginx の qr_verify ゾーン（10r/m）で行う
    - 失敗時のエラーは統一（QR 存在リーク防止）
    - entry_session_token は管理 API では使用不可（type 不一致で 401）
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.qr import QrVerifyRequest, QrVerifyResponse
from app.services.qr_verify import QrVerifyService

router = APIRouter(prefix="/qr", tags=["public-qr"])


@router.post(
    "/verify",
    response_model=QrVerifyResponse,
    summary="QR コード + PIN を検証してセッショントークンを発行",
    description="""
QR コードに埋め込まれたトークンと PIN を検証します。

- **pin_required=False** の QR コードは `pin` フィールド不要です
- **pin_required=True** の QR コードは `pin` フィールドが必須です
- PIN を連続 **{max_attempts}** 回間違えると一時的にブロックされます

成功すると **30 分間** 有効な `entry_session_token` が返ります。
このトークンを使って入場申請フォームを送信できます。
""",
    responses={
        200: {"description": "認証成功。entry_session_token を返す"},
        401: {"description": "QR コードが無効 / 期限切れ / PIN 誤り"},
        422: {"description": "リクエスト形式エラー（PIN が数字以外など）"},
        429: {"description": "PIN 試行回数超過。Retry-After ヘッダーを確認してください"},
    },
)
async def verify_qr(
    body: QrVerifyRequest,
    db: AsyncSession = Depends(get_db),
) -> QrVerifyResponse:
    """
    QR トークン + PIN を検証して entry_session_token を返す。

    フロントエンドは受け取ったトークンを以降のリクエストで
    `Authorization: Bearer <entry_session_token>` として送信する。
    """
    service = QrVerifyService(db)
    return await service.verify(body)
