"""
監査ログ (Audit Logging)

セキュリティに関係するイベントを JSON 形式で記録する。
通常の操作ログ（RequestLoggingMiddleware）とは別に、
「誰が」「いつ」「何をしたか」を追跡可能にする。

JSON 形式で出力するため、Loki / CloudWatch / Elasticsearch 等への転送が容易。

イベント種別:
  auth.login_success      — ログイン成功
  auth.login_failure      — ログイン失敗（パスワード不一致）
  auth.login_locked       — ロック中のアカウントへのアクセス試行
  auth.login_inactive     — 無効化アカウントへのアクセス試行
  auth.token_refresh      — リフレッシュトークンによるアクセストークン再発行
  auth.logout             — ログアウト（リフレッシュトークン失効）
  qr.create               — QR コード作成
  qr.deactivate           — QR コード無効化
  qr.activate             — QR コード再有効化
  qr.verify_success       — QR + PIN 認証成功（入場セッション発行）
  qr.verify_block         — QR PIN ブルートフォースによるブロック発生
  entry.approve           — 入場申請承認
  entry.reject            — 入場申請却下
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

# RequestLoggingMiddleware が設定する request_id コンテキスト変数を参照
# import は遅延させてサーキュラーインポートを回避
_audit_logger = logging.getLogger("audit")


def _get_request_id() -> str:
    """現在のリクエスト ID を返す（コンテキスト変数から取得）"""
    try:
        from app.middleware.logging import request_id_var  # noqa: PLC0415
        return request_id_var.get("")
    except Exception:
        return ""


def _emit(
    event_type: str,
    *,
    user_id: str | None = None,
    user_email: str | None = None,
    site_id: str | None = None,
    qr_id: str | None = None,
    entry_id: str | None = None,
    ip: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """
    監査イベントを JSON 形式でログに書き出す。

    出力例:
        {"ts":"2026-05-21T10:00:00+00:00","event":"auth.login_success",
         "req_id":"a1b2c3d4","user_id":"uuid","user_email":"admin@example.com",
         "role":"admin","ip":"192.168.1.1"}
    """
    record: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        "req_id": _get_request_id(),
    }
    if user_id is not None:
        record["user_id"] = user_id
    if user_email is not None:
        record["user_email"] = user_email
    if site_id is not None:
        record["site_id"] = site_id
    if qr_id is not None:
        record["qr_id"] = qr_id
    if entry_id is not None:
        record["entry_id"] = entry_id
    if ip is not None:
        record["ip"] = ip
    if extra:
        record.update(extra)

    _audit_logger.info(json.dumps(record, ensure_ascii=False))


# =============================================================================
# 認証イベント
# =============================================================================

def login_success(
    email: str,
    user_id: str,
    role: str,
    ip: str | None = None,
) -> None:
    """ログイン成功"""
    _emit("auth.login_success", user_email=email, user_id=user_id, ip=ip,
          extra={"role": role})


def login_failure(
    email: str,
    ip: str | None = None,
    reason: str = "bad_password",
) -> None:
    """ログイン失敗（パスワード不一致）"""
    _emit("auth.login_failure", user_email=email, ip=ip,
          extra={"reason": reason})


def login_locked(email: str, ip: str | None = None) -> None:
    """ロック中アカウントへのアクセス試行"""
    _emit("auth.login_locked", user_email=email, ip=ip)


def login_inactive(email: str, ip: str | None = None) -> None:
    """無効化アカウントへのアクセス試行"""
    _emit("auth.login_inactive", user_email=email, ip=ip)


def token_refresh(user_id: str, email: str) -> None:
    """リフレッシュトークンによるアクセストークン再発行"""
    _emit("auth.token_refresh", user_id=user_id, user_email=email)


def logout(user_id: str, email: str) -> None:
    """ログアウト（リフレッシュトークン失効）"""
    _emit("auth.logout", user_id=user_id, user_email=email)


# =============================================================================
# QR イベント
# =============================================================================

def qr_create(
    user_id: str,
    site_id: str,
    qr_id: str,
    label: str | None,
) -> None:
    """QR コード作成"""
    _emit("qr.create", user_id=user_id, site_id=site_id, qr_id=qr_id,
          extra={"label": label})


def qr_deactivate(user_id: str, qr_id: str, site_id: str) -> None:
    """QR コード無効化"""
    _emit("qr.deactivate", user_id=user_id, qr_id=qr_id, site_id=site_id)


def qr_activate(user_id: str, qr_id: str, site_id: str) -> None:
    """QR コード再有効化"""
    _emit("qr.activate", user_id=user_id, qr_id=qr_id, site_id=site_id)


def qr_verify_success(
    qr_id: str,
    site_id: str,
    ip: str | None = None,
    pin_required: bool = False,
) -> None:
    """QR + PIN 認証成功（入場セッション発行）"""
    _emit("qr.verify_success", qr_id=qr_id, site_id=site_id, ip=ip,
          extra={"pin_required": pin_required})


def qr_verify_block(qr_id: str, site_id: str, ip: str | None = None) -> None:
    """QR PIN ブルートフォースによるブロック発生"""
    _emit("qr.verify_block", qr_id=qr_id, site_id=site_id, ip=ip)


# =============================================================================
# 入場申請イベント
# =============================================================================

def entry_approve(
    user_id: str,
    entry_id: str,
    site_id: str,
) -> None:
    """入場申請承認"""
    _emit("entry.approve", user_id=user_id, entry_id=entry_id, site_id=site_id)


def entry_reject(
    user_id: str,
    entry_id: str,
    site_id: str,
    reason: str | None = None,
) -> None:
    """入場申請却下"""
    _emit("entry.reject", user_id=user_id, entry_id=entry_id, site_id=site_id,
          extra={"reason": reason} if reason else None)
