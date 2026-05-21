/**
 * バックエンド API の TypeScript 型定義
 * backend/app/schemas/ と対応させる
 */

// =============================================================================
// 共通
// =============================================================================

export interface ApiError {
  detail: string | { msg: string; type: string; loc: string[] }[]
}

// =============================================================================
// QR 認証
// =============================================================================

export interface QrVerifyRequest {
  token: string
  pin?: string
}

export interface PublicSiteInfo {
  id: string
  name: string
  require_health_check: boolean
  require_insurance: boolean
  custom_notice: string | null
}

export interface QrVerifyResponse {
  entry_session_token: string
  token_type: string
  expires_in: number
  site: PublicSiteInfo
}

// =============================================================================
// 作業員
// =============================================================================

export interface WorkerLookupRequest {
  phone: string
}

export interface WorkerSummary {
  id: string
  last_name: string
  first_name: string
  last_name_kana: string | null
  first_name_kana: string | null
  worker_type: string
  affiliation_company: string | null
  job_title: string | null
}

export interface WorkerLookupResponse {
  exists: boolean
  worker: WorkerSummary | null
}

// =============================================================================
// Draft 作成・更新
// =============================================================================

export interface DraftCreateRequest {
  phone: string
  worker_id?: string
  last_name?: string
  first_name?: string
}

/** PATCH 用: 送信したフィールドのみが更新される */
export interface DraftUpdateRequest {
  // Worker fields
  last_name?: string
  first_name?: string
  last_name_kana?: string
  first_name_kana?: string
  birth_date?: string       // "YYYY-MM-DD"
  gender?: string
  blood_type?: string
  worker_type?: string
  affiliation_company?: string
  job_title?: string
  postal_code?: string
  address?: string
  emergency_contact?: string
  emergency_contact_name?: string
  emergency_contact_relation?: string
  insurance_type?: string
  insurance_number?: string
  // Entry fields
  planned_entry_date?: string  // "YYYY-MM-DD"
  has_health_check?: boolean
  health_check_date?: string   // "YYYY-MM-DD"
  consent_agreed?: boolean
}

export interface WorkerInEntry {
  id: string
  last_name: string
  first_name: string
  last_name_kana: string | null
  first_name_kana: string | null
  phone: string | null
  birth_date: string | null
  gender: string | null
  blood_type: string | null
  worker_type: string
  affiliation_company: string | null
  job_title: string | null
  postal_code: string | null
  address: string | null
  emergency_contact: string | null
  emergency_contact_name: string | null
  insurance_type: string | null
  insurance_number: string | null
  consent_agreed_at: string | null
}

export interface DraftEntryResponse {
  id: string
  receipt_number: string
  status: string
  site_id: string
  qr_code_id: string
  planned_entry_date: string | null
  has_health_check: boolean
  health_check_date: string | null
  draft_started_at: string | null
  last_saved_at: string | null
  worker: WorkerInEntry
  warnings: string[]
}

export interface SubmitResponse {
  id: string
  receipt_number: string
  status: string
  submitted_at: string
  site_name: string
}

// =============================================================================
// 管理者認証
// =============================================================================

export interface LoginRequest {
  email: string
  password: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

/**
 * Phase 8: トークンローテーション対応
 * refresh エンドポイントは新しい refresh_token も返す。
 * フロントエンドは旧 refresh_token を破棄してこの値を保存すること。
 */
export interface AccessTokenResponse {
  access_token: string
  refresh_token: string   // ローテーションで新たに発行
  token_type: string
}

export interface LogoutResponse {
  message: string
}

export interface CurrentUser {
  id: string
  email: string
  name: string
  role: 'super_admin' | 'admin' | 'supervisor'
  company_id: string
}

// =============================================================================
// 管理者 — 申請一覧
// =============================================================================

export type EntryStatus = 'draft' | 'pending' | 'approved' | 'rejected' | 'withdrawn'

export interface WorkerSummaryInList {
  id: string
  last_name: string
  first_name: string
  last_name_kana: string | null
  first_name_kana: string | null
  worker_type: string
  affiliation_company: string | null
  job_title: string | null
}

export interface EntryListItem {
  id: string
  receipt_number: string
  status: EntryStatus
  site_id: string
  site_name: string
  planned_entry_date: string | null
  submitted_at: string | null
  worker: WorkerSummaryInList
}

export interface PendingListResponse {
  items: EntryListItem[]
  total: number
  page: number
  per_page: number
  has_next: boolean
}

// =============================================================================
// 管理者 — 申請詳細
// =============================================================================

export interface WorkerDetailInEntry {
  id: string
  last_name: string
  first_name: string
  last_name_kana: string | null
  first_name_kana: string | null
  phone: string | null
  birth_date: string | null
  gender: string | null
  blood_type: string | null
  worker_type: string
  affiliation_company: string | null
  job_title: string | null
  postal_code: string | null
  address: string | null
  emergency_contact: string | null
  emergency_contact_name: string | null
  emergency_contact_relation: string | null
  insurance_type: string | null
  insurance_number: string | null
  consent_agreed_at: string | null
}

export interface ApprovalLogItem {
  id: string
  actor_id: string
  actor_name: string | null
  action: 'approved' | 'rejected' | 'withdrawn'
  reason: string | null
  created_at: string
}

export interface EntryDetailResponse {
  id: string
  receipt_number: string
  status: EntryStatus
  site_id: string
  site_name: string
  qr_code_id: string
  planned_entry_date: string | null
  has_health_check: boolean
  health_check_date: string | null
  approved_by: string | null
  approved_at: string | null
  rejection_reason: string | null
  draft_started_at: string | null
  submitted_at: string | null
  worker: WorkerDetailInEntry
  approval_logs: ApprovalLogItem[]
}

// =============================================================================
// 管理者 — 承認・差戻し
// =============================================================================

export interface ApproveRequest {
  reason?: string
}

export interface RejectRequest {
  reason: string
}

export interface ApprovalResultResponse {
  id: string
  receipt_number: string
  status: EntryStatus
  approved_by: string | null
  approved_at: string | null
  rejection_reason: string | null
}

// =============================================================================
// 管理者 — 現場管理
// =============================================================================

export interface SiteListItem {
  id: string
  name: string
  address: string | null
  start_date: string | null    // "YYYY-MM-DD"
  end_date: string | null      // "YYYY-MM-DD"
  is_active: boolean
  supervisor_id: string | null
  supervisor_name: string | null
  active_qr_count: number
  pending_entry_count: number
}

export interface SiteListResponse {
  items: SiteListItem[]
  total: number
  page: number
  per_page: number
  has_next: boolean
}

// =============================================================================
// 管理者 — QR コード
// =============================================================================

export interface QrCodeItem {
  id: string
  label: string | null
  is_active: boolean
  pin_required: boolean
  max_uses: number | null
  use_count: number
  blocked_count: number
  expires_at: string | null    // ISO 8601
  last_accessed_at: string | null
  failed_attempts: number
  deactivated_at: string | null
  created_by_name: string | null
  created_at: string
}

export interface SiteDetailResponse {
  id: string
  name: string
  address: string | null
  start_date: string | null
  end_date: string | null
  is_active: boolean
  require_health_check: boolean
  require_insurance: boolean
  custom_notice: string | null
  supervisor_id: string | null
  supervisor_name: string | null
  qr_codes: QrCodeItem[]
  pending_entry_count: number
}

export interface QrCreateRequest {
  label?: string
  pin_required?: boolean
  pin?: string
  expires_at?: string | null   // ISO 8601
  max_uses?: number | null
}

export interface QrCreateResponse {
  id: string
  token: string                // QR URL 生成用: /entry/<token>
  label: string | null
  pin_required: boolean
  max_uses: number | null
  expires_at: string | null
  use_count: number
  blocked_count: number
  created_at: string
}

export interface QrUpdateRequest {
  label: string | null
  expires_at: string | null
  max_uses: number | null
}

export interface QrStatusResponse {
  id: string
  is_active: boolean
  deactivated_at: string | null
}

// =============================================================================
// Phase 9 — 超短縮再入場フロー
// =============================================================================

export interface QuickMatchRequest {
  phone: string
  birth_month: number
  birth_day: number
}

export interface QuickMatchResponse {
  matched: boolean
  worker: WorkerSummary | null
}

// =============================================================================
// Phase 9 — 運用・UX 改善
// =============================================================================

export interface SiteBadge {
  site_id: string
  site_name: string
  pending_count: number
  stale_count: number
}

export interface PendingBadgeResponse {
  total_pending: number
  total_stale: number
  sites: SiteBadge[]
}

export interface MorningEntryItem {
  id: string
  receipt_number: string
  status: string
  site_id: string
  site_name: string
  planned_entry_date: string | null
  submitted_at: string | null
  worker_name: string
  worker_type: string
  affiliation_company: string | null
  job_title: string | null
  is_stale: boolean
}

export interface MorningBriefResponse {
  today: string
  pending_count: number
  approved_count: number
  entries: MorningEntryItem[]
}

export interface MetricsSummaryResponse {
  period_days: number
  total_submissions: number
  total_approved: number
  total_rejected: number
  avg_approval_minutes: number | null
  pending_over_30min: number
}

export type FeedbackCategory = 'input_hard' | 'poor_connection' | 'unclear' | 'other'

export interface FeedbackRequest {
  category: FeedbackCategory
  detail?: string
  site_id?: string
}

export interface FeedbackResponse {
  id: string
  message: string
}
