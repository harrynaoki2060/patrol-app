/**
 * 管理者 現場・QR コード管理 API クライアント
 */

import { apiFetch } from './client'
import type {
  QrCodeItem,
  QrCreateRequest,
  QrCreateResponse,
  QrStatusResponse,
  QrUpdateRequest,
  SiteDetailResponse,
  SiteListResponse,
} from '@/types/api'

const ADMIN = '/api/admin'

// =============================================================================
// 現場
// =============================================================================

export interface SiteListParams {
  page?: number
  per_page?: number
}

export async function getSites(
  params: SiteListParams = {},
  token: string,
): Promise<SiteListResponse> {
  const q = new URLSearchParams()
  if (params.page)     q.set('page', String(params.page))
  if (params.per_page) q.set('per_page', String(params.per_page))
  const qs = q.toString() ? `?${q}` : ''
  return apiFetch<SiteListResponse>(`${ADMIN}/sites${qs}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function getSiteDetail(
  siteId: string,
  token: string,
): Promise<SiteDetailResponse> {
  return apiFetch<SiteDetailResponse>(`${ADMIN}/sites/${siteId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

// =============================================================================
// QR コード
// =============================================================================

export async function createQr(
  siteId: string,
  req: QrCreateRequest,
  token: string,
): Promise<QrCreateResponse> {
  return apiFetch<QrCreateResponse>(`${ADMIN}/sites/${siteId}/qr`, {
    method: 'POST',
    body: req,
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function updateQr(
  qrId: string,
  req: QrUpdateRequest,
  token: string,
): Promise<QrCodeItem> {
  return apiFetch<QrCodeItem>(`${ADMIN}/qr/${qrId}`, {
    method: 'PATCH',
    body: req,
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function deactivateQr(
  qrId: string,
  token: string,
): Promise<QrStatusResponse> {
  return apiFetch<QrStatusResponse>(`${ADMIN}/qr/${qrId}/deactivate`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function activateQr(
  qrId: string,
  token: string,
): Promise<QrStatusResponse> {
  return apiFetch<QrStatusResponse>(`${ADMIN}/qr/${qrId}/activate`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
}
