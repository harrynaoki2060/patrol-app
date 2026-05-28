"""
AdminUser 関連 Pydantic スキーマ
"""
from datetime import datetime

from pydantic import BaseModel, EmailStr


class AdminUserSchema(BaseModel):
    """DB モデルから変換する管理者情報（パスワードハッシュを含まない）"""

    id: str
    company_id: str
    email: EmailStr
    name: str
    role: str
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CurrentUserSchema(BaseModel):
    """
    GET /api/admin/auth/me のレスポンス。
    トークンから復元できる情報 + DB から取得した最新情報。
    """

    id: str
    email: str
    name: str
    role: str
    company_id: str
    is_active: bool
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}
