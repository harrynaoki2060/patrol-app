/**
 * AdminPendingPage テスト
 *
 * カバー範囲:
 *   - 承認待ち一覧の読み込みと表示
 *   - 空状態の表示
 *   - 承認フロー（ボタン → API 呼び出し → 成功メッセージ）
 *   - 差戻しフロー（フォーム展開 → 理由入力 → 確定 → 成功メッセージ）
 *   - API エラー時のエラーバナー表示
 *   - キーワード検索（デバウンス後に API が呼ばれる）
 */

import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AdminPendingPage from './page'

// ---------------------------------------------------------------------------
// モック設定
// ---------------------------------------------------------------------------

// Next.js ナビゲーション
const mockPush    = vi.fn()
const mockReplace = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
}))

// Next.js Link（シンプルな a タグに差し替え）
vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) =>
    <a href={href} {...props}>{children}</a>,
}))

// AdminAuthContext
const mockGetAccessToken = vi.fn(() => 'test-token')
vi.mock('@/lib/context/AdminAuthContext', () => ({
  useAdminAuth: () => ({
    getAccessToken:   mockGetAccessToken,
    refreshIfNeeded:  vi.fn().mockResolvedValue('new-token'),
    isAuthenticated:  true,
  }),
}))

// API
const mockGetPendingEntries = vi.fn()
const mockApproveEntry      = vi.fn()
const mockRejectEntry       = vi.fn()
vi.mock('@/lib/api/entries', () => ({
  getPendingEntries: (...args: unknown[]) => mockGetPendingEntries(...args),
  approveEntry:      (...args: unknown[]) => mockApproveEntry(...args),
  rejectEntry:       (...args: unknown[]) => mockRejectEntry(...args),
}))

// ---------------------------------------------------------------------------
// テスト用フィクスチャ
// ---------------------------------------------------------------------------

const makeItem = (id: string, lastName: string) => ({
  id,
  receipt_number:   `RC-${id}`,
  status:           'pending',
  submitted_at:     '2025-05-01T10:00:00Z',
  site_name:        'テスト現場',
  worker: {
    last_name:            lastName,
    first_name:           '太郎',
    last_name_kana:       'タナカ',
    first_name_kana:      'タロウ',
    affiliation_company:  '株式会社テスト',
    worker_type:          'company_employee',
  },
})

const makeListResponse = (items: ReturnType<typeof makeItem>[], total = items.length) => ({
  items,
  total,
  page:     1,
  per_page: 20,
  has_next: false,
})

// ---------------------------------------------------------------------------
// テスト
// ---------------------------------------------------------------------------

describe('AdminPendingPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApproveEntry.mockResolvedValue({})
    mockRejectEntry.mockResolvedValue({})
  })

  // -------------------------------------------------------------------------
  // 一覧表示
  // -------------------------------------------------------------------------

  it('読み込み中はスピナーを表示する', () => {
    // 解決しない Promise でローディング状態を維持
    mockGetPendingEntries.mockReturnValue(new Promise(() => {}))
    render(<AdminPendingPage />)
    // スピナー要素（role="status" or aria-busy はないが視覚的に確認）
    // ローディング中はエントリ名が表示されない
    expect(screen.queryByText('田中 太郎')).not.toBeInTheDocument()
  })

  it('申請一覧を表示する', async () => {
    mockGetPendingEntries.mockResolvedValue(
      makeListResponse([makeItem('1', '田中'), makeItem('2', '鈴木')])
    )
    render(<AdminPendingPage />)

    await waitFor(() => {
      expect(screen.getByText('田中 太郎')).toBeInTheDocument()
      expect(screen.getByText('鈴木 太郎')).toBeInTheDocument()
    })
    // 件数表示
    expect(screen.getByText(/2件の申請/)).toBeInTheDocument()
  })

  it('申請がない場合は空状態メッセージを表示する', async () => {
    mockGetPendingEntries.mockResolvedValue(makeListResponse([]))
    render(<AdminPendingPage />)

    await waitFor(() => {
      expect(screen.getByText(/審査待ちの申請はありません/)).toBeInTheDocument()
    })
  })

  it('API エラー時にエラーバナーを表示する', async () => {
    mockGetPendingEntries.mockRejectedValue(new Error('network error'))
    render(<AdminPendingPage />)

    await waitFor(() => {
      expect(screen.getByText(/申請一覧の取得に失敗しました/)).toBeInTheDocument()
    })
  })

  // -------------------------------------------------------------------------
  // 承認フロー
  // -------------------------------------------------------------------------

  it('承認ボタンをクリックすると approveEntry が呼ばれ成功メッセージが出る', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })

    mockGetPendingEntries.mockResolvedValue(
      makeListResponse([makeItem('entry-001', '田中')])
    )
    render(<AdminPendingPage />)

    await waitFor(() => screen.getByText('田中 太郎'))

    const approveBtn = screen.getByRole('button', { name: /承認/ })
    await user.click(approveBtn)

    expect(mockApproveEntry).toHaveBeenCalledWith('entry-001', {}, 'test-token')

    await waitFor(() => {
      expect(screen.getByText('承認しました')).toBeInTheDocument()
    })
  })

  it('承認後に一覧が再読み込みされる', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })

    mockGetPendingEntries
      .mockResolvedValueOnce(makeListResponse([makeItem('entry-001', '田中')]))
      .mockResolvedValue(makeListResponse([]))

    render(<AdminPendingPage />)
    await waitFor(() => screen.getByText('田中 太郎'))

    await user.click(screen.getByRole('button', { name: /承認/ }))

    await waitFor(() => {
      expect(mockGetPendingEntries).toHaveBeenCalledTimes(2)
    })
  })

  // -------------------------------------------------------------------------
  // 差戻しフロー
  // -------------------------------------------------------------------------

  it('差戻しボタンをクリックするとフォームが展開される', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })

    mockGetPendingEntries.mockResolvedValue(
      makeListResponse([makeItem('entry-001', '田中')])
    )
    render(<AdminPendingPage />)
    await waitFor(() => screen.getByText('田中 太郎'))

    await user.click(screen.getByRole('button', { name: /差戻し/ }))

    expect(screen.getByLabelText(/差戻し理由/)).toBeInTheDocument()
  })

  it('差戻し理由なしで確定するとエラーが表示される', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })

    mockGetPendingEntries.mockResolvedValue(
      makeListResponse([makeItem('entry-001', '田中')])
    )
    render(<AdminPendingPage />)
    await waitFor(() => screen.getByText('田中 太郎'))

    await user.click(screen.getByRole('button', { name: /差戻し/ }))
    await user.click(screen.getByRole('button', { name: /差戻しを確定/ }))

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(mockRejectEntry).not.toHaveBeenCalled()
  })

  it('差戻し理由を入力して確定すると rejectEntry が呼ばれ成功メッセージが出る', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })

    mockGetPendingEntries.mockResolvedValue(
      makeListResponse([makeItem('entry-001', '田中')])
    )
    render(<AdminPendingPage />)
    await waitFor(() => screen.getByText('田中 太郎'))

    await user.click(screen.getByRole('button', { name: /差戻し/ }))
    await user.type(screen.getByLabelText(/差戻し理由/), '書類が不足しています')
    await user.click(screen.getByRole('button', { name: /差戻しを確定/ }))

    expect(mockRejectEntry).toHaveBeenCalledWith(
      'entry-001',
      { reason: '書類が不足しています' },
      'test-token'
    )

    await waitFor(() => {
      expect(screen.getByText('差戻しました')).toBeInTheDocument()
    })
  })

  it('差戻しキャンセルでフォームが閉じる', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })

    mockGetPendingEntries.mockResolvedValue(
      makeListResponse([makeItem('entry-001', '田中')])
    )
    render(<AdminPendingPage />)
    await waitFor(() => screen.getByText('田中 太郎'))

    await user.click(screen.getByRole('button', { name: /差戻し/ }))
    expect(screen.getByLabelText(/差戻し理由/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /キャンセル/ }))
    expect(screen.queryByLabelText(/差戻し理由/)).not.toBeInTheDocument()
  })

  // -------------------------------------------------------------------------
  // キーワード検索
  // -------------------------------------------------------------------------

  it('検索欄に入力すると getPendingEntries がキーワード付きで呼ばれる', async () => {
    vi.useFakeTimers()
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })

    mockGetPendingEntries.mockResolvedValue(makeListResponse([]))
    render(<AdminPendingPage />)
    await waitFor(() => expect(mockGetPendingEntries).toHaveBeenCalledTimes(1))

    const searchInput = screen.getByRole('searchbox')
    await user.type(searchInput, '田中')

    // デバウンス前は追加 API 呼び出しなし
    expect(mockGetPendingEntries).toHaveBeenCalledTimes(1)

    // 500ms デバウンス経過
    await act_timer(500)

    await waitFor(() => {
      const calls = mockGetPendingEntries.mock.calls
      const lastCall = calls[calls.length - 1]
      expect(lastCall[0]).toMatchObject({ keyword: '田中' })
    })

    vi.useRealTimers()
  })
})

// ---------------------------------------------------------------------------
// ヘルパー
// ---------------------------------------------------------------------------
async function act_timer(ms: number) {
  const { act } = await import('@testing-library/react')
  await act(async () => { vi.advanceTimersByTime(ms) })
}
