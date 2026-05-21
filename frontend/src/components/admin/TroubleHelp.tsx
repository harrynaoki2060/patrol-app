'use client'

/**
 * TroubleHelp — QR エラー・トラブル時のサポート案内
 *
 * 表示条件:
 *   - QR コードが無効だった場合
 *   - QR アクセスがブロックされた場合
 *   - ネットワーク接続できない場合
 *
 * 機能:
 *   - 紙フォールバック案内モーダル
 *   - 担当者へのトラブル報告フロー説明
 *   - 手動受付の連絡先情報表示
 */

import { useState } from 'react'

interface TroubleHelpProps {
  /** 現場名（わかる場合） */
  siteName?: string
  /** 担当者への連絡先（わかる場合） */
  contactInfo?: string
}

interface PaperFallbackModalProps {
  siteName?: string
  onClose: () => void
}

function PaperFallbackModal({ siteName, onClose }: PaperFallbackModalProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center"
      role="dialog"
      aria-modal="true"
      aria-label="紙での対応手順"
    >
      {/* オーバーレイ */}
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* モーダル */}
      <div className="relative w-full max-w-lg bg-white rounded-t-2xl p-6 pb-10 animate-slide-up">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-bold text-gray-900 text-lg">📋 紙での入場対応</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-2xl min-h-[44px] min-w-[44px] flex items-center justify-center"
            aria-label="閉じる"
          >
            ×
          </button>
        </div>

        <div className="space-y-4 text-sm text-gray-700">
          <p>
            QR コードが使えない場合は、紙の入場届で対応してください。
          </p>

          <div className="bg-yellow-50 rounded-xl p-4 space-y-2">
            <p className="font-bold text-gray-900">📝 紙対応の手順</p>
            <ol className="list-decimal list-inside space-y-1 text-gray-700">
              <li>現場事務所の「入場届」用紙を受け取る</li>
              <li>氏名・所属会社・入場日・職種を記入する</li>
              <li>担当者（監督）に提出する</li>
              <li>担当者が後でシステムに入力する</li>
            </ol>
          </div>

          {siteName && (
            <div className="bg-gray-50 rounded-xl p-3">
              <p className="text-xs text-gray-500">現場名</p>
              <p className="font-medium text-gray-900">{siteName}</p>
            </div>
          )}

          <div className="bg-blue-50 rounded-xl p-4">
            <p className="font-bold text-gray-900 mb-1">ℹ️ 担当者へ伝えること</p>
            <ul className="list-disc list-inside space-y-1 text-gray-700">
              <li>QR コードが読み込めなかった</li>
              <li>自分の氏名・電話番号</li>
              <li>所属会社・職種</li>
            </ul>
          </div>

          <button
            onClick={onClose}
            className="btn-primary mt-4"
          >
            わかりました
          </button>
        </div>
      </div>
    </div>
  )
}

export function TroubleHelp({ siteName, contactInfo }: TroubleHelpProps) {
  const [expanded, setExpanded]       = useState(false)
  const [showPaperModal, setShowPaperModal] = useState(false)

  return (
    <>
      <div className="w-full max-w-sm">
        {/* トラブル案内トグル */}
        <button
          onClick={() => setExpanded(e => !e)}
          className="w-full text-sm text-gray-500 hover:text-gray-700 flex items-center justify-center gap-2 min-h-[44px] py-2"
          aria-expanded={expanded}
        >
          <span>困っていますか？</span>
          <span className="text-xs">{expanded ? '▲' : '▼'}</span>
        </button>

        {expanded && (
          <div className="card space-y-3 animate-fade-in">
            {/* 紙フォールバック */}
            <button
              onClick={() => setShowPaperModal(true)}
              className="w-full text-left p-3 rounded-xl bg-yellow-50 hover:bg-yellow-100 transition-colors"
            >
              <p className="text-sm font-medium text-yellow-900">📋 紙で入場する</p>
              <p className="text-xs text-yellow-700 mt-0.5">
                QR が使えない場合の代替手順を確認する
              </p>
            </button>

            {/* 担当者に連絡 */}
            <div className="p-3 rounded-xl bg-blue-50">
              <p className="text-sm font-medium text-blue-900">📞 担当者に連絡する</p>
              {contactInfo ? (
                <p className="text-sm text-blue-800 mt-0.5 font-medium">{contactInfo}</p>
              ) : (
                <p className="text-xs text-blue-700 mt-0.5">
                  現場の監督・管理者にこのエラーを見せてください
                </p>
              )}
            </div>

            {/* QR 無効のヒント */}
            <div className="p-3 rounded-xl bg-gray-50">
              <p className="text-sm font-medium text-gray-700">🔍 よくある原因</p>
              <ul className="text-xs text-gray-600 mt-1 space-y-1 list-disc list-inside">
                <li>QR コードの有効期限切れ</li>
                <li>PIN コードの入力間違い</li>
                <li>ネットワーク接続の問題</li>
              </ul>
            </div>
          </div>
        )}
      </div>

      {/* 紙フォールバックモーダル */}
      {showPaperModal && (
        <PaperFallbackModal
          siteName={siteName}
          onClose={() => setShowPaperModal(false)}
        />
      )}
    </>
  )
}
