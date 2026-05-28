"""
認証関連 Pydantic スキーマ

入力バリデーション・レスポンスシリアライズを担う。
パスワードはレスポンスに絶対含めない（exclude=True を徹底）。

Phase 8 追加:
  - LogoutRequest    : POST /api/admin/auth/logout のリクエストボディ
  - TokenRotationResponse: refresh エンドポイントが新 refresh_token も返す
"""
from pydantic import BaseModel, EmailStr, Field

from app.core.config import settings


# =============================================================================
# リクエスト
# =============================================================================

class LoginRequest(BaseModel):
    """POST /api/admin/auth/login のリクエストボディ"""

    email: EmailStr = Field(..., description="メールアドレス")
    password: str = Field(..., min_length=1, max_length=128, description="パスワード")

    model_config = {
        "json_schema_extra": {
            "example": {"email": "admin@example.com", "password": "Secret1234!"}
        }
    }


class RefreshRequest(BaseModel):
    """POST /api/admin/auth/refresh のリクエストボディ"""

    refresh_token: str = Field(..., description="リフレッシュトークン")


class LogoutRequest(BaseModel):
    """POST /api/admin/auth/logout のリクエストボディ"""

    refresh_token: str = Field(..., description="失効させるリフレッシュトークン")


# =============================================================================
# レスポンス
# =============================================================================

class _UserInToken(BaseModel):
    """トークンレスポンスに含むユーザー情報（最小限）"""

    id: str
    email: str
    name: str
    role: str


class TokenResponse(BaseModel):
    """
    POST /api/admin/auth/login のレスポンス。
    access_token と refresh_token を両方返す。
    """

    access_token: str = Field(..., description="アクセストークン（Bearer）")
    refresh_token: str = Field(..., description="リフレッシュトークン（更新用）")
    token_type: str = Field(default="bearer", description="トークン種別")
    expires_in: int = Field(
        default=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        description="アクセストークンの有効秒数",
    )
    user: _UserInToken = Field(..., description="ログインユーザー情報")


class TokenRotationResponse(BaseModel):
    """
    POST /api/admin/auth/refresh のレスポンス（Phase 8 — トークンローテーション対応）。

    - access_token: 新しいアクセストークン（30 分有効）
    - refresh_token: ローテーションで新たに発行した refresh_token
      → フロントエンドは旧 refresh_token を破棄してこれを保存すること
    """

    access_token: str = Field(..., description="新しいアクセストークン")
    refresh_token: str = Field(..., description="新しいリフレッシュトークン（ローテーション）")
    token_type: str = Field(default="bearer")
    expires_in: int = Field(default=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)


# 後方互換のエイリアス（テストコードが参照しているため維持）
AccessTokenResponse = TokenRotationResponse


class LogoutResponse(BaseModel):
    """POST /api/admin/auth/logout のレスポンス"""

    message: str = Field(default="ログアウトしました")
