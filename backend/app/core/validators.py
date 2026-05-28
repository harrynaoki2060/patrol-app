"""
入力バリデーション・正規化ユーティリティ

作業員フォームで使用する各種バリデーションを提供する。
Pydantic field_validator から呼び出されることを想定。

設計方針:
  - 正規化関数 (normalize_*): 副作用なし。変換後の文字列を返す。
  - バリデーション関数 (validate_*): 問題があれば ValueError を raise する。
  - 警告 (warn_*): 問題があれば警告メッセージを返す（エラーにしない）。
  - 全て純粋関数（外部依存なし）。テストしやすい。
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timezone

# =============================================================================
# 電話番号
# =============================================================================

_PHONE_STRIP_PATTERN = re.compile(r"[\s\-－ー（）()．. 　]")
_PHONE_VALID_PATTERN = re.compile(r"^0\d{9,10}$")


def normalize_phone(phone: str) -> str:
    """
    電話番号を正規化する。

    処理:
      1. 全角数字 → 半角数字
      2. ハイフン・スペース・括弧などの区切り文字を除去
      3. 先頭の +81 (国際形式) → 0 に変換

    Returns:
        ハイフンなしの半角数字文字列（例: "09012345678"）

    Raises:
        ValueError: 正規化後に電話番号として不正な形式の場合
    """
    # 全角 → 半角変換
    normalized = unicodedata.normalize("NFKC", phone)
    # 区切り文字を除去
    normalized = _PHONE_STRIP_PATTERN.sub("", normalized)
    # 国際形式 +81 → 0
    if normalized.startswith("+81"):
        normalized = "0" + normalized[3:]

    if not _PHONE_VALID_PATTERN.match(normalized):
        raise ValueError(
            f"電話番号の形式が正しくありません（0から始まる10〜11桁の数字）: {phone!r}"
        )
    return normalized


# =============================================================================
# カタカナ
# =============================================================================

_KANA_PATTERN = re.compile(r"^[ァ-ヶーヴ\s　]+$")


def validate_kana(value: str, field_name: str = "カナ") -> str:
    """
    カタカナ文字列を検証する。

    許可: 全角カタカナ（ァ-ヶ）、長音符（ー）、濁点付き文字（ヴ）、スペース

    Returns:
        入力値（変換なし）

    Raises:
        ValueError: カタカナ以外の文字が含まれる場合
    """
    if not value:
        return value
    # 全角スペースを半角スペースに統一して検証
    check_value = value.replace("　", " ")
    if not _KANA_PATTERN.match(check_value):
        raise ValueError(f"{field_name}はカタカナで入力してください")
    return value


# =============================================================================
# 生年月日
# =============================================================================

_MIN_AGE_YEARS = 15       # 年少者保護: 15歳未満は警告
_WARN_AGE_YEARS = 75      # 高齢者警告: 75歳以上は確認推奨
_MAX_AGE_YEARS = 120      # 非現実的な年齢の上限


def validate_birth_date(birth_date: date) -> date:
    """
    生年月日を検証する。

    検証内容:
      1. 未来日付の禁止
      2. 非現実的な過去日付の禁止（120 年以上前）

    Returns:
        入力値（変換なし）

    Raises:
        ValueError: 未来の日付 / 非現実的な過去日付
    """
    today = date.today()

    if birth_date > today:
        raise ValueError("生年月日に未来の日付は指定できません")

    age = (today - birth_date).days // 365
    if age > _MAX_AGE_YEARS:
        raise ValueError(f"生年月日が正しくありません（{_MAX_AGE_YEARS}年以上前の日付）")

    return birth_date


def get_age_warning(birth_date: date) -> str | None:
    """
    年齢に関する警告メッセージを返す（エラーにはしない）。

    Returns:
        警告メッセージ（問題なければ None）
    """
    today = date.today()
    age = (today - birth_date).days // 365

    if age < _MIN_AGE_YEARS:
        return f"作業員の年齢が {age} 歳です。年少者（{_MIN_AGE_YEARS}歳未満）の就労には法的確認が必要です"
    if age >= _WARN_AGE_YEARS:
        return f"作業員の年齢が {age} 歳です。高齢者健康確認を推奨します"
    return None


# =============================================================================
# 入場予定日
# =============================================================================

def validate_planned_entry_date(planned_date: date) -> date:
    """
    入場予定日を検証する。

    検証内容:
      - 過去の日付を許容しない（今日以降のみ）

    Returns:
        入力値（変換なし）

    Raises:
        ValueError: 過去の日付
    """
    today = date.today()
    if planned_date < today:
        raise ValueError("入場予定日に過去の日付は指定できません")
    return planned_date


# =============================================================================
# 健康診断日
# =============================================================================

_HEALTH_CHECK_VALID_YEARS = 1  # 1年以内の健康診断のみ有効とする


def validate_health_check_date(health_check_date: date) -> date:
    """
    健康診断実施日を検証する。

    検証内容:
      - 未来日付の禁止
      - 有効期限（1年以内）チェック（警告レベル: raise しない）

    Returns:
        入力値（変換なし）

    Raises:
        ValueError: 未来の日付
    """
    today = date.today()
    if health_check_date > today:
        raise ValueError("健康診断日に未来の日付は指定できません")
    return health_check_date


def get_health_check_warning(health_check_date: date) -> str | None:
    """健康診断の有効期限（1年）を超えている場合に警告を返す"""
    today = date.today()
    days_elapsed = (today - health_check_date).days
    if days_elapsed > 365:
        return f"健康診断から {days_elapsed} 日経過しています。有効期限（1年）を超えています"
    return None


# =============================================================================
# 郵便番号
# =============================================================================

_POSTAL_STRIP = re.compile(r"[\s\-－]")
_POSTAL_VALID = re.compile(r"^\d{7}$")


def normalize_postal_code(postal_code: str) -> str:
    """
    郵便番号を正規化する（ハイフン除去・全角→半角）。

    Returns:
        7桁の半角数字文字列（例: "1234567"）

    Raises:
        ValueError: 7桁の数字でない場合
    """
    normalized = unicodedata.normalize("NFKC", postal_code)
    normalized = _POSTAL_STRIP.sub("", normalized)
    if not _POSTAL_VALID.match(normalized):
        raise ValueError("郵便番号は7桁の数字で入力してください（例: 1234567 または 123-4567）")
    return normalized


# =============================================================================
# 緊急連絡先電話番号
# =============================================================================

def validate_emergency_contact(contact: str) -> str:
    """
    緊急連絡先電話番号を正規化・検証する。
    normalize_phone() と同じ処理を適用する。
    """
    return normalize_phone(contact)
