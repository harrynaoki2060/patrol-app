'use client'

/**
 * 高齢者モード コンテキスト
 *
 * 有効時:
 *   - フォントサイズ拡大（text-xl 相当）
 *   - ボタン高さ拡大（min-h-[72px]）
 *   - 高コントラスト（背景白・文字黒）
 *   - タッチターゲット拡大
 *
 * 設定は localStorage に永続化（ページをまたいで引き継がれる）。
 * body に .elderly-mode クラスを付与し、globals.css で CSS 変数を切り替える。
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from 'react'

interface ElderlyModeContextValue {
  enabled: boolean
  toggle: () => void
}

const ElderlyModeContext = createContext<ElderlyModeContextValue>({
  enabled: false,
  toggle: () => {},
})

const STORAGE_KEY = 'elderly_mode'

export function ElderlyModeProvider({ children }: { children: React.ReactNode }) {
  const [enabled, setEnabled] = useState(false)

  // 初期化: localStorage から復元
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved === 'true') {
        setEnabled(true)
        document.body.classList.add('elderly-mode')
      }
    } catch {
      // SSR や localStorage 使用不可の場合は無視
    }
  }, [])

  const toggle = useCallback(() => {
    setEnabled(prev => {
      const next = !prev
      try {
        if (next) {
          localStorage.setItem(STORAGE_KEY, 'true')
          document.body.classList.add('elderly-mode')
        } else {
          localStorage.removeItem(STORAGE_KEY)
          document.body.classList.remove('elderly-mode')
        }
      } catch {
        // ignore
      }
      return next
    })
  }, [])

  return (
    <ElderlyModeContext.Provider value={{ enabled, toggle }}>
      {children}
    </ElderlyModeContext.Provider>
  )
}

export function useElderlyMode() {
  return useContext(ElderlyModeContext)
}
