/**
 * 公開 API（認証不要 or entry_session_token 必須）
 *
 * - POST /api/public/qr/verify          → entry_session 取得
 * - POST /api/public/workers/lookup      → 作業員検索（entry_session 必須）
 * - POST /api/public/entries/draft       → Draft 作成（entry_session 必須）
 * - PATCH /api/public/entries/{id}       → Draft 更新（entry_session 必須）
 * - POST /api/public/entries/{id}/submit → 申請確定（entry_session 必須）
 */

import { apiFetch } from './client'
import type {
  DraftCreateRequest,
  DraftEntryResponse,
  DraftUpdateRequest,
  QrVerifyRequest,
  QrVerifyResponse,
  QuickMatchRequest,
  QuickMatchResponse,
  SubmitResponse,
  WorkerLookupRequest,
  WorkerLookupResponse,
} from '@/types/api'

// ---------------------------------------------------------------------------
// QR 認証（認証不要）
// ---------------------------------------------------------------------------

export async function verifyQr(req: QrVerifyRequest): Promise<QrVerifyResponse> {
  return apiFetch<QrVerifyResponse>('/public/qr/verify', {
    method: 'POST',
    body: req,
  })
}

// ---------------------------------------------------------------------------
// 超短縮再入場フロー（entry_session 必須）
// ---------------------------------------------------------------------------

export async function quickMatchWorker(
  req: QuickMatchRequest,
  sessionToken: string,
): Promise<QuickMatchResponse> {
  return apiFetch<QuickMatchResponse>('/public/workers/quick-match', {
    method: 'POST',
    body: req,
    token: sessionToken,
  })
}

// ---------------------------------------------------------------------------
// 作業員検索（entry_session 必須）
// ---------------------------------------------------------------------------

export async function lookupWorker(
  req: WorkerLookupRequest,
  sessionToken: string,
): Promise<WorkerLookupResponse> {
  return apiFetch<WorkerLookupResponse>('/public/workers/lookup', {
    method: 'POST',
    body: req,
    token: sessionToken,
  })
}

// ---------------------------------------------------------------------------
// Draft CRUD（entry_session 必須）
// ---------------------------------------------------------------------------

export async function createDraft(
  req: DraftCreateRequest,
  sessionToken: string,
): Promise<DraftEntryResponse> {
  return apiFetch<DraftEntryResponse>('/public/entries/draft', {
    method: 'POST',
    body: req,
    token: sessionToken,
  })
}

export async function updateDraft(
  entryId: string,
  req: DraftUpdateRequest,
  sessionToken: string,
): Promise<DraftEntryResponse> {
  return apiFetch<DraftEntryResponse>(`/public/entries/${entryId}`, {
    method: 'PATCH',
    body: req,
    token: sessionToken,
  })
}

export async function submitEntry(
  entryId: string,
  sessionToken: string,
): Promise<SubmitResponse> {
  return apiFetch<SubmitResponse>(`/public/entries/${entryId}/submit`, {
    method: 'POST',
    token: sessionToken,
  })
}
