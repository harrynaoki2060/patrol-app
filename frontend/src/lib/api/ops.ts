/**
 * 管理者 運用・UX 改善 API（Phase 9）
 *
 * - GET  /api/admin/badges           → pending バッジカウント
 * - GET  /api/admin/morning-brief    → 朝礼モード
 * - GET  /api/admin/metrics/summary  → 運用メトリクス
 * - POST /api/admin/feedback         → UX フィードバック
 */

import { apiFetch } from './client'
import type {
  FeedbackRequest,
  FeedbackResponse,
  MetricsSummaryResponse,
  MorningBriefResponse,
  PendingBadgeResponse,
} from '@/types/api'

export async function getPendingBadges(
  token: string,
): Promise<PendingBadgeResponse> {
  return apiFetch<PendingBadgeResponse>('/admin/badges', {
    method: 'GET',
    token,
  })
}

export async function getMorningBrief(
  token: string,
): Promise<MorningBriefResponse> {
  return apiFetch<MorningBriefResponse>('/admin/morning-brief', {
    method: 'GET',
    token,
  })
}

export async function getMetricsSummary(
  token: string,
): Promise<MetricsSummaryResponse> {
  return apiFetch<MetricsSummaryResponse>('/admin/metrics/summary', {
    method: 'GET',
    token,
  })
}

export async function submitFeedback(
  req: FeedbackRequest,
  token: string,
): Promise<FeedbackResponse> {
  return apiFetch<FeedbackResponse>('/admin/feedback', {
    method: 'POST',
    body: req,
    token,
  })
}
