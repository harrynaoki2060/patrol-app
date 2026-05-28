/**
 * Vitest グローバルセットアップ
 *
 * - @testing-library/jest-dom のカスタムマッチャーを有効化
 * - window.matchMedia のモック（jsdom では未実装）
 * - sessionStorage のリセット
 */

import '@testing-library/jest-dom'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

// jsdom は matchMedia を実装していないため空モックを提供
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches:             false,
    media:               query,
    onchange:            null,
    addListener:         vi.fn(),
    removeListener:      vi.fn(),
    addEventListener:    vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent:       vi.fn(),
  })),
})

// 各テスト後にレンダリングツリーをクリーンアップし、sessionStorage をリセット
afterEach(() => {
  cleanup()
  sessionStorage.clear()
})
