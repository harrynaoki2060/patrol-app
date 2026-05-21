"""
作業員関連 Pydantic スキーマ

公開 API 向けの作業員検索リクエスト・レスポンスを定義する。

セキュリティ設計:
  - WorkerSummary は最小限の情報のみ返す
    ※ birth_date / address / insurance_number / phone は含めない
    ※ 氏名＋所属＋職種のみ（フロントの「前回情報を使用しますか？」表示用）
  - inactive な作業員は検索結果に含めない
  - 他現場の入場状況は一切返さない
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.core.validators import normalize_phone


# =============================================================================
# リクエスト
# =============================================================================

class WorkerLookupRequest(BaseModel):
    """
    POST /api/public/workers/lookup のリクエストボディ。

    phone: 電話番号（正規化前の生入力を受け取り、サービス層で正規化する）
    """

    phone: str = Field(
        ...,
        min_length=10,
        max_length=15,
        description="電話番号（ハイフンあり・なし両方可。0から始まる10〜11桁）",
    )

    @field_validator("phone")
    @classmethod
    def phone_must_be_valid(cls, v: str) -> str:
        """normalize_phone が ValueError を raise すれば Pydantic 422 に変換される"""
        return normalize_phone(v)

    model_config = {
        "json_schema_extra": {
            "example": {"phone": "090-1234-5678"}
        }
    }


# =============================================================================
# レスポンス
# =============================================================================

class WorkerSummary(BaseModel):
    """
    作業員の要約情報（公開側 API での返却用・最小情報）。

    含める情報:
      - id         : worker_id（Draft Create で worker_id として使用）
      - 氏名       : last_name / first_name / kana
      - 所属       : affiliation_company / worker_type
      - 職種       : job_title

    含めない情報（個人情報保護）:
      - phone / phone_normalized
      - birth_date
      - address / postal_code
      - emergency_contact / emergency_contact_name
      - insurance_type / insurance_number
      - consent_agreed_at
    """

    id: str = Field(..., description="作業員 ID（Draft Create の worker_id に使用）")
    last_name: str = Field(..., description="姓")
    first_name: str = Field(..., description="名")
    last_name_kana: str | None = Field(None, description="姓カナ")
    first_name_kana: str | None = Field(None, description="名カナ")
    worker_type: str = Field(..., description="区分（company_employee / sole_proprietor）")
    affiliation_company: str | None = Field(None, description="所属会社名")
    job_title: str | None = Field(None, description="職種・工種")


class QuickMatchRequest(BaseModel):
    """
    POST /api/public/workers/quick-match のリクエスト。

    既存作業員を「電話番号 + 生年月日(月日のみ)」で照合する。
    フルの生年月日ではなく月日のみを要求することで、
    既存登録作業員が記憶しやすい最小限の認証を実現する。
    """

    phone: str = Field(
        ...,
        min_length=10,
        max_length=15,
        description="電話番号（ハイフンあり・なし両方可）",
    )
    birth_month: int = Field(
        ...,
        ge=1,
        le=12,
        description="生年月日の月（1〜12）",
    )
    birth_day: int = Field(
        ...,
        ge=1,
        le=31,
        description="生年月日の日（1〜31）",
    )

    @field_validator("phone")
    @classmethod
    def phone_must_be_valid(cls, v: str) -> str:
        return normalize_phone(v)

    model_config = {
        "json_schema_extra": {
            "example": {
                "phone": "090-1234-5678",
                "birth_month": 3,
                "birth_day": 15,
            }
        }
    }


class QuickMatchResponse(BaseModel):
    """
    POST /api/public/workers/quick-match のレスポンス。

    matched=True の場合: worker に WorkerSummary が入る
    matched=False の場合: worker は None

    セキュリティ:
      - 電話番号のみ / 月日のみの部分一致では matched=True を返さない
      - inactive 作業員は matched=False として返す（存在リーク防止）
      - 電話番号が存在するか否かは matched=False と区別しない
    """

    matched: bool = Field(..., description="電話番号 + 生年月日(月日)が一致するアクティブな作業員が存在するか")
    worker: WorkerSummary | None = Field(
        None,
        description="作業員の要約情報（matched=True の場合のみ）",
    )


class WorkerLookupResponse(BaseModel):
    """
    POST /api/public/workers/lookup のレスポンス。

    exists=False の場合: worker は None
    exists=True  の場合: worker に WorkerSummary が入る

    フロントエンドは exists=True の場合に「前回情報を使用しますか？」
    ダイアログを表示し、ユーザーが Yes なら worker.id を使って Draft Create を行う。
    """

    exists: bool = Field(..., description="電話番号に紐づくアクティブな作業員が存在するか")
    worker: WorkerSummary | None = Field(
        None,
        description="作業員の要約情報（exists=True の場合のみ）",
    )
