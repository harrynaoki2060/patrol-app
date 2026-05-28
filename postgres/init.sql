-- =============================================================================
-- 建設工事 新規入場管理システム - PostgreSQL 初期化
-- このファイルはコンテナ初回起動時に自動実行される
-- =============================================================================

-- データベース設定
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;

-- 拡張機能（UUID生成など）
-- NOTE: アプリ側（Python uuid モジュール）で UUID を生成するため不要
-- CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- TODO: Day2 で Alembic マイグレーションによりテーブルを作成します
-- 以下のテーブルは IMPLEMENTATION_PLAN.md の DBスキーマ固定 セクションを参照:
--   - companies
--   - admin_users
--   - sites
--   - site_qr_codes
--   - workers
--   - worker_site_entries
--   - approval_logs
-- =============================================================================

-- 動作確認用クエリ（コンテナ起動時にエラーがないことを確認）
SELECT 'Database initialized successfully' AS status;
