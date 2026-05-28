"""
アプリケーション設定
環境変数を Pydantic Settings で型安全に管理する
"""
import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # 未定義の環境変数は無視
    )

    # -------------------------------------------------------------------------
    # データベース
    # -------------------------------------------------------------------------
    DATABASE_URL: str = (
        "postgresql+asyncpg://app:changeme_dev_password@postgres:5432/entry_db"
    )

    # -------------------------------------------------------------------------
    # Redis
    # -------------------------------------------------------------------------
    REDIS_URL: str = "redis://:changeme_dev_password@redis:6379/0"

    # -------------------------------------------------------------------------
    # MinIO (ファイルストレージ)
    # -------------------------------------------------------------------------
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "changeme_dev_password"
    MINIO_BUCKET: str = "entry-documents"
    MINIO_USE_SSL: bool = False

    # -------------------------------------------------------------------------
    # JWT 認証
    # -------------------------------------------------------------------------
    # 本番では必ず 32 文字以上のランダム文字列に変更すること
    # 生成例: python -c "import secrets; print(secrets.token_hex(32))"
    SECRET_KEY: str = "CHANGE_THIS_IN_PRODUCTION_" + secrets.token_hex(8)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # -------------------------------------------------------------------------
    # ログインロック
    # -------------------------------------------------------------------------
    MAX_LOGIN_FAILURES: int = 5          # この回数連続失敗でロック
    ACCOUNT_LOCK_MINUTES: int = 30       # ロック継続時間（分）

    # -------------------------------------------------------------------------
    # 公開 QR セッション
    # -------------------------------------------------------------------------
    ENTRY_SESSION_EXPIRE_MINUTES: int = 30   # QR → PIN 後に発行する entry_session の有効期限（分）
    QR_BLOCK_MINUTES: int = 15               # PIN 連続失敗後のブロック継続時間（分）

    # -------------------------------------------------------------------------
    # CORS
    # カンマ区切り文字列 → リストに変換
    # -------------------------------------------------------------------------
    ALLOWED_ORIGINS: str = "http://localhost,http://localhost:3000"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]

    # -------------------------------------------------------------------------
    # ログ
    # -------------------------------------------------------------------------
    LOG_LEVEL: str = "INFO"

    # -------------------------------------------------------------------------
    # アプリケーション情報
    # -------------------------------------------------------------------------
    APP_TITLE: str = "建設工事 新規入場管理システム API"
    APP_VERSION: str = "0.1.0"


# シングルトンとしてインポートして使う
settings = Settings()
