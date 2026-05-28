/**
 * 管理者向け 入場申請 API
 *
 * - GET  /api/admin/entries/pending         → pending 一覧
 * - GET  /api/admin/entries/{id}            → 申請詳細
 * - POST /api/admin/entries/{id}/approve    → 承認
 * - POST /api/admin/entries/{id}/reject     → 差戻し
 */

import { apiFetch } from './client'
import type {
  ApprovalResultResponse,
  ApproveRequest,
  EntryDetailResponse,
  PendingListResponse,
  RejectRequest,
} from '@/types/api'

export interface PendingListParams {
  page?: number
  per_page?: number
  keyword?: string
  site_id?: string
}

export async function getPendingEntries(
  params: PendingListParams,
  accessToken: string,
): Promise<PendingListResponse> {
  const qs = new URLSearchParams()
  if (params.page)     qs.set('page',     String(params.page))
  if (params.per_page) qs.set('per_page', String(params.per_page))
  if (params.keyword)  qs.set('keyword',  params.keyword)
  if (params.site_id)  qs.set('site_id',  params.site_id)

  const query = qs.toString() ? `?${qs.toString()}` : ''
  return apiFetch<PendingListResponse>(`/admin/entries/pending${query}`, {
    method: 'GET',
    token: accessToken,
  })
}

export async function getEntryDetail(
  entryId: string,
  accessToken: string,
): Promise<EntryDetailResponse> {
  return apiFetch<EntryDetailResponse>(`/admin/entries/${entryId}`, {
    method: 'GET',
    token: accessToken,
  })
}

export async function approveEntry(
  entryId: string,
  req: ApproveRequest,
  accessToken: string,
): Promise<ApprovalResultResponse> {
  return apiFetch<ApprovalResultResponse>(`/admin/entries/${entryId}/approve`, {
    method: 'POST',
    body: req,
    token: accessToken,
  })
}

export async function rejectEntry(
  entryId: string,
  req: RejectRequest,
  accessToken: string,
): Promise<ApprovalResultResponse> {
  return apiFetch<ApprovalResultResponse>(`/admin/entries/${entryId}/reject`, {
    method: 'POST',
    body: req,
    token: accessToken,
  })
}
