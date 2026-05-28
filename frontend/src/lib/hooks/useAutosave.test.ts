/**
 * useAutosave フック テスト
 *
 * カバー範囲:
 *   - デバウンスタイミング（debounceMs 後に onSave が呼ばれる）
 *   - 連続 triggerSave でタイマーがリセットされる
 *   - flush() で即時保存
 *   - enabled=false のとき保存しない
 *   - 保存中の重複実行防止
 *   - status の遷移（idle → pending → saving → saved / error）
 */

import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useAutosave } from './useAutosave'

describe('useAutosave', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // ---------------------------------------------------------------------------
  // デバウンスタイミング
  // ---------------------------------------------------------------------------

  it('debounceMs 経過後に onSave が呼ばれる', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() =>
      useAutosave({ data: { name: 'テスト' }, onSave, debounceMs: 3000 })
    )

    act(() => { result.current.triggerSave() })
    expect(onSave).not.toHaveBeenCalled()
    expect(result.current.status).toBe('pending')

    await act(async () => { vi.advanceTimersByTime(3000) })
    expect(onSave).toHaveBeenCalledTimes(1)
    expect(result.current.status).toBe('saved')
  })

  it('debounceMs 未満では onSave が呼ばれない', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() =>
      useAutosave({ data: { name: 'テスト' }, onSave, debounceMs: 3000 })
    )

    act(() => { result.current.triggerSave() })
    act(() => { vi.advanceTimersByTime(2999) })

    expect(onSave).not.toHaveBeenCalled()
  })

  // ---------------------------------------------------------------------------
  // タイマーリセット
  // ---------------------------------------------------------------------------

  it('連続して triggerSave するとタイマーがリセットされる', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() =>
      useAutosave({ data: { name: 'テスト' }, onSave, debounceMs: 3000 })
    )

    act(() => { result.current.triggerSave() })
    act(() => { vi.advanceTimersByTime(2000) })
    act(() => { result.current.triggerSave() }) // タイマーリセット
    act(() => { vi.advanceTimersByTime(2000) }) // 合計4秒経過、最後のtriggerから2秒

    expect(onSave).not.toHaveBeenCalled()

    await act(async () => { vi.advanceTimersByTime(1000) }) // 最後のtriggerから3秒
    expect(onSave).toHaveBeenCalledTimes(1)
  })

  // ---------------------------------------------------------------------------
  // flush（即時保存）
  // ---------------------------------------------------------------------------

  it('flush() はタイマーをキャンセルして即時保存する', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() =>
      useAutosave({ data: { name: 'テスト' }, onSave, debounceMs: 3000 })
    )

    act(() => { result.current.triggerSave() })
    expect(onSave).not.toHaveBeenCalled()

    await act(async () => { await result.current.flush() })
    expect(onSave).toHaveBeenCalledTimes(1)
  })

  it('flush() 後にタイマーが残っていても二重に保存しない', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() =>
      useAutosave({ data: { name: 'テスト' }, onSave, debounceMs: 3000 })
    )

    act(() => { result.current.triggerSave() })
    await act(async () => { await result.current.flush() })
    await act(async () => { vi.advanceTimersByTime(5000) })

    // flush + タイマー発火で2回にはならない
    expect(onSave).toHaveBeenCalledTimes(1)
  })

  // ---------------------------------------------------------------------------
  // enabled フラグ
  // ---------------------------------------------------------------------------

  it('enabled=false のとき triggerSave は何もしない', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() =>
      useAutosave({ data: { name: 'テスト' }, onSave, debounceMs: 3000, enabled: false })
    )

    act(() => { result.current.triggerSave() })
    await act(async () => { vi.advanceTimersByTime(5000) })

    expect(onSave).not.toHaveBeenCalled()
    expect(result.current.status).toBe('idle')
  })

  it('enabled=false のとき flush() は何もしない', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() =>
      useAutosave({ data: { name: 'テスト' }, onSave, debounceMs: 3000, enabled: false })
    )

    await act(async () => { await result.current.flush() })

    expect(onSave).not.toHaveBeenCalled()
  })

  // ---------------------------------------------------------------------------
  // エラーハンドリング
  // ---------------------------------------------------------------------------

  it('onSave が throw すると status が error になる', async () => {
    const onSave = vi.fn().mockRejectedValue(new Error('保存失敗'))
    const { result } = renderHook(() =>
      useAutosave({ data: { name: 'テスト' }, onSave, debounceMs: 1000 })
    )

    act(() => { result.current.triggerSave() })
    await act(async () => { vi.advanceTimersByTime(1000) })

    expect(result.current.status).toBe('error')
  })

  // ---------------------------------------------------------------------------
  // lastSaved
  // ---------------------------------------------------------------------------

  it('保存成功後に lastSaved が設定される', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() =>
      useAutosave({ data: { name: 'テスト' }, onSave, debounceMs: 1000 })
    )

    expect(result.current.lastSaved).toBeNull()

    act(() => { result.current.triggerSave() })
    await act(async () => { vi.advanceTimersByTime(1000) })

    expect(result.current.lastSaved).toBeInstanceOf(Date)
  })

  it('保存失敗後は lastSaved が更新されない', async () => {
    const onSave = vi.fn().mockRejectedValue(new Error('失敗'))
    const { result } = renderHook(() =>
      useAutosave({ data: { name: 'テスト' }, onSave, debounceMs: 1000 })
    )

    act(() => { result.current.triggerSave() })
    await act(async () => { vi.advanceTimersByTime(1000) })

    expect(result.current.lastSaved).toBeNull()
  })

  // ---------------------------------------------------------------------------
  // 重複保存防止
  // ---------------------------------------------------------------------------

  it('保存中に flush() を呼んでも重複しない', async () => {
    let resolveSave!: () => void
    const onSave = vi.fn().mockImplementation(
      () => new Promise<void>(resolve => { resolveSave = resolve })
    )
    const { result } = renderHook(() =>
      useAutosave({ data: { name: 'テスト' }, onSave, debounceMs: 1000 })
    )

    act(() => { result.current.triggerSave() })
    await act(async () => { vi.advanceTimersByTime(1000) }) // doSave 開始、未完了

    // 保存中に flush を呼んでも追加呼び出しにならない
    await act(async () => {
      result.current.flush() // fire-and-forget
      resolveSave()           // 保存完了
    })

    expect(onSave).toHaveBeenCalledTimes(1)
  })
})
