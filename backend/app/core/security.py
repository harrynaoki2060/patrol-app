"""
セキュリティユーティリティ

JWT トークンの発行・検証と bcrypt パスワードハッシュ化を提供する。

設計方針:
  - HS256 (HMAC-SHA256) を採用。環境変数 SECRET_KEY で署名
  - access token      : 30 分。payload に role / name を含める（DB 問い合わせを最小化）
  - refresh token     : 7 日。payload は最小（sub + type + jti のみ）
  - entry_session     : 30 分。QR → PIN 成功後の公開申請用ショートセッション
                        sub なし（未登録作業員のため）。site_id / qr_code_id のみ。
  - jti (JWT ID)      : 将来のブラックリスト機能に対応できる UUID を付与
  - token version(ver): ユーザー単位でトークンを一括無効化できる設計

トークン種別ごとのアクセス制御:
  - type="access"        → 管理 API にアクセス可能（deps.py の get_current_user）
  - type="refresh"       → トークン再発行専用
  - type="entry_session" → 公開申請 API にのみアクセス可能（public_deps.py）
    ※ entry_session を管理 API に使うと type 不一致で 401 になる
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# =============================================================================
# パスワードハッシュ
# =============================================================================
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """
    平文パスワードを bcrypt ハッシュに変換する。
    返り値を DB に保存する。
    """
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    平文パスワードと bcrypt ハッシュを照合する。
    タイミング攻撃に対して安全（常時一定時間で処理）。
    """
    return _pwd_context.verify(plain_password, hashed_password)


# =============================================================================
# JWT
# =============================================================================

# トークン種別定数
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"
TOKEN_TYPE_ENTRY_SESSION = "entry_session"

# entry_session の有効期限（分）— 実効値は settings.ENTRY_SESSION_EXPIRE_MINUTES
ENTRY_SESSION_EXPIRE_MINUTES = 30  # kept for backward-compat imports; settings takes precedence


def create_access_token(
    *,
    user_id: str,
    email: str,
    role: str,
    name: str,
    token_version: int = 1,
) -> str:
    """
    アクセストークンを発行する。

    payload:
        sub   : user_id
        email : メールアドレス（表示用）
        role  : AdminRole の値（認可チェックに使用）
        name  : 表示名
        type  : "access"
        ver   : トークンバージョン（将来の一括無効化に使用）
        iat   : 発行日時
        exp   : 有効期限
        jti   : JWT ID（将来のブラックリストに使用）
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "role": role,
        "name": name,
        "type": TOKEN_TYPE_ACCESS,
        "ver": token_version,
        "iat": int(now.timestamp()),
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(*, user_id: str) -> str:
    """
    リフレッシュトークンを発行する。

    payload は最小限（sub + type + jti）のみ。
    アクセストークン再発行時には DB から最新の user 情報を取得する。
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    payload: dict[str, Any] = {
        "sub": user_id,
        "type": TOKEN_TYPE_REFRESH,
        "iat": int(now.timestamp()),
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    """
    JWT を検証してペイロードを返す。

    検証内容:
      - 署名の正当性
      - 有効期限 (exp)

    Returns:
        有効な場合は payload dict、無効な場合は None
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError:
        return None


def decode_access_token(token: str) -> dict[str, Any] | None:
    """
    アクセストークン専用の検証。type == "access" であることも確認する。
    """
    payload = decode_token(token)
    if payload is None:
        return None
    if payload.get("type") != TOKEN_TYPE_ACCESS:
        return None
    return payload


def decode_refresh_token(token: str) -> dict[str, Any] | None:
    """
    リフレッシュトークン専用の検証。type == "refresh" であることも確認する。
    """
    payload = decode_token(token)
    if payload is None:
        return None
    if payload.get("type") != TOKEN_TYPE_REFRESH:
        return None
    return payload


# =============================================================================
# Entry Session Token（公開申請用ショートセッション）
# =============================================================================

def create_entry_session_token(*, site_id: str, qr_code_id: str) -> str:
    """
    QR → PIN 成功後に発行する公開申請セッショントークン。

    payload:
        type        : "entry_session"（管理 API と分離するための識別子）
        site_id     : 現場 ID（申請先の固定）
        qr_code_id  : 使用した QR コード ID（申請時の追跡）
        iat         : 発行日時
        exp         : 有効期限（30 分）
        jti         : JWT ID（将来の無効化に使用）

    設計ポイント:
        - sub（ユーザー ID）がない。QR を通過した匿名セッションのため。
        - type="access" でないため deps.py の get_current_user では 401 になる。
        - refresh 不要。期限切れは再度 QR を読み込む。
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ENTRY_SESSION_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "type": TOKEN_TYPE_ENTRY_SESSION,
        "site_id": site_id,
        "qr_code_id": qr_code_id,
        "iat": int(now.timestamp()),
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_entry_session_token(token: str) -> dict[str, Any] | None:
    """
    公開申請セッショントークンを検証して payload を返す。
    type == "entry_session" であることも確認する。
    """
    payload = decode_token(token)
    if payload is None:
        return None
    if payload.get("type") != TOKEN_TYPE_ENTRY_SESSION:
        return None
    return payload
