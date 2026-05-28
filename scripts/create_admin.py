#!/usr/bin/env python3
"""
初期管理者作成スクリプト

使い方（Docker コンテナ内）:
    python scripts/create_admin.py --email admin@example.com --password Secret1234! --name "管理者" --role super_admin

    # または環境変数で指定
    ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD=Secret1234! python scripts/create_admin.py

実行方法:
    docker compose exec backend python scripts/create_admin.py \\
        --email admin@example.com \\
        --password "Secret1234!" \\
        --name "システム管理者" \\
        --role super_admin \\
        --company-name "株式会社テスト"

注意:
    - このスクリプトは開発・初回セットアップ専用
    - 本番環境では安全な方法でパスワードを渡すこと（環境変数 or シークレット管理）
    - 既存のメールアドレスが存在する場合は上書きしない（エラーで終了）
"""
import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path

# backend/ ディレクトリを sys.path に追加
_here = Path(__file__).resolve().parent.parent / "backend"
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import hash_password
from app.models.admin_user import AdminRole, AdminUser
from app.models.company import Company


async def create_admin(
    email: str,
    password: str,
    name: str,
    role: str,
    company_name: str,
) -> None:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionLocal() as session:
        # ロールバリデーション
        valid_roles = [r.value for r in AdminRole]
        if role not in valid_roles:
            print(f"❌ 無効なロール: {role}")
            print(f"   有効なロール: {', '.join(valid_roles)}")
            sys.exit(1)

        # メール重複チェック
        existing = await session.execute(
            select(AdminUser).where(AdminUser.email == email.lower().strip())
        )
        if existing.scalar_one_or_none() is not None:
            print(f"❌ このメールアドレスはすでに登録されています: {email}")
            sys.exit(1)

        # 会社を取得または作成
        company_result = await session.execute(
            select(Company).where(Company.name == company_name)
        )
        company = company_result.scalar_one_or_none()

        if company is None:
            company = Company(
                id=str(uuid.uuid4()),
                name=company_name,
                is_active=True,
            )
            session.add(company)
            await session.flush()
            print(f"✅ 会社を作成しました: {company_name} (id={company.id})")
        else:
            print(f"ℹ️  既存の会社を使用します: {company_name} (id={company.id})")

        # 管理者ユーザーを作成
        admin = AdminUser(
            id=str(uuid.uuid4()),
            company_id=company.id,
            email=email.lower().strip(),
            password_hash=hash_password(password),
            name=name,
            role=role,
            is_active=True,
            login_failure_count=0,
        )
        session.add(admin)
        await session.commit()

    await engine.dispose()

    print(f"""
✅ 管理者を作成しました
   ID      : {admin.id}
   メール  : {admin.email}
   名前    : {admin.name}
   ロール  : {admin.role}
   会社 ID : {admin.company_id}

ログインテスト:
   curl -X POST http://localhost/api/admin/auth/login \\
     -H "Content-Type: application/json" \\
     -d '{{"email": "{admin.email}", "password": "<パスワード>"}}'
""")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="初期管理者アカウントを作成する",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--email", help="メールアドレス（ログイン ID）")
    parser.add_argument("--password", help="パスワード（省略するとプロンプトで入力）")
    parser.add_argument("--name", default="システム管理者", help="表示名")
    parser.add_argument(
        "--role",
        choices=[r.value for r in AdminRole],
        default=AdminRole.SUPER_ADMIN.value,
        help=f"ロール（デフォルト: {AdminRole.SUPER_ADMIN.value}）",
    )
    parser.add_argument("--company-name", default="管理会社", help="所属会社名")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # email が未指定の場合はプロンプトで入力
    email = args.email or os.environ.get("ADMIN_EMAIL")
    if not email:
        email = input("メールアドレス: ").strip()
    if not email:
        print("❌ メールアドレスは必須です")
        sys.exit(1)

    # password が未指定の場合はプロンプトで入力（エコーバックなし）
    password = args.password or os.environ.get("ADMIN_PASSWORD")
    if not password:
        password = getpass("パスワード: ")
        password_confirm = getpass("パスワード（確認）: ")
        if password != password_confirm:
            print("❌ パスワードが一致しません")
            sys.exit(1)

    if len(password) < 8:
        print("❌ パスワードは 8 文字以上にしてください")
        sys.exit(1)

    print(f"\n管理者を作成します...")
    print(f"  メール : {email}")
    print(f"  名前   : {args.name}")
    print(f"  ロール : {args.role}")
    print(f"  会社   : {args.company_name}")

    asyncio.run(
        create_admin(
            email=email,
            password=password,
            name=args.name,
            role=args.role,
            company_name=args.company_name,
        )
    )


if __name__ == "__main__":
    main()
