"""
QR コード関連 Pydantic スキーマ

公開側 QR 認証リクエスト・レスポンスを定義する。

設計ポイント:
  - QrVerifyRequest: token + optional PIN のみ。他情報は一切含めない
  - QrVerifyResponse: entry_session_token + site の最小情報のみ返す
    ※ QR ID・PIN ハッシュ・失敗回数などの内部情報はレスポンスに含めない
  - token は 1〜128 文字に制限（無限長 token によるサービス攻撃を防ぐ）
  - pin は 4〜8 桁の数字のみ許可（bcrypt コストを一定範囲内に保つ）
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.schemas.site import PublicSiteInfo


# =============================================================================
# リクエスト
# =============================================================================

class QrVerifyRequest(BaseModel):
    """
    POST /api/public/qr/verify のリクエストボディ。

    token  : QR コード URL に埋め込まれたランダムトークン（64 文字想定）
    pin    : PIN 必須 QR の場合のみ必要。数字 4〜8 桁。
             PIN 不要 QR に対して pin を送っても無視する（エラーにしない）。
    """

    token: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="QR コードに埋め込まれたトークン",
    )
    pin: str | None = Field(
        default=None,
        min_length=4,
        max_length=8,
        description="PIN（4〜8 桁の数字。pin_required=True の QR のみ必須）",
    )

    @field_validator("pin")
    @classmethod
    def pin_must_be_digits(cls, v: str | None) -> str | None:
        """PIN は数字のみ許可する。アルファベット混入によるペイロード膨張を防ぐ。"""
        if v is not None and not v.isdigit():
            raise ValueError("PIN は数字のみ使用できます")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "token": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                "pin": "1234",
            }
        }
    }


# =============================================================================
# レスポンス
# =============================================================================

class QrVerifyResponse(BaseModel):
    """
    POST /api/public/qr/verify の成功レスポンス。

    entry_session_token : 30 分有効の公開申請用 JWT（type="entry_session"）
    token_type          : 常に "bearer"
    expires_in          : entry_session の有効秒数（フロントのタイマー表示用）
    site                : 入場フォーム表示に必要な最小限の現場情報
    """

    entry_session_token: str = Field(
        ...,
        description="公開申請セッショントークン（Bearer として使用）",
    )
    token_type: str = Field(
        default="bearer",
        description="トークン種別",
    )
    expires_in: int = Field(
        default=settings.ENTRY_SESSION_EXPIRE_MINUTES * 60,
        description="entry_session_token の有効秒数",
    )
    site: PublicSiteInfo = Field(
        ...,
        description="現場情報（入場フォームの表示制御に使用）",
    )
