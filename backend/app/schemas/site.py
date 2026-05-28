"""
Site スキーマ

公開側に返す現場情報は最小限に絞る（内部管理情報は含めない）。
"""
from pydantic import BaseModel


class PublicSiteInfo(BaseModel):
    """
    QR 認証成功後に公開エンドポイントが返す現場情報。

    設計ポイント:
      - company_id / supervisor_id / address などの管理情報は含めない
      - require_health_check / require_insurance はフロントのフォーム表示制御に必要
      - custom_notice は QR ランディングページに表示する現場固有の注意事項
    """

    id: str
    name: str
    require_health_check: bool
    require_insurance: bool
    custom_notice: str | None = None
