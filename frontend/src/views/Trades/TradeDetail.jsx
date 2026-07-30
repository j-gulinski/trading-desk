import { useEffect, useRef, useState } from 'react'
import { usePolling } from '../../hooks/usePolling.js'
import { apiGet, apiPost } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import { normalizeAuditEvents } from '../../domain/auditEvents.js'
import { tradeDetailOf } from '../../domain/trades.js'
import { buildCloseTradeIntent } from '../../domain/tradeActions.js'
import { BLOTTER_POLL_INTERVAL_MS } from '../../config/trades.js'
import TradeDetailDialog from '../../components/trades/TradeDetailDialog.jsx'

const CLOSE_STALL_MS = 15000

export default function TradeDetail({ row, bookNames, onClose }) {
  const detail = usePolling(
    ({ signal }) => apiGet(endpoints.blotter.trade(row.trade.id), { signal }),
    { intervalMs: BLOTTER_POLL_INTERVAL_MS },
  )
  const detailData = tradeDetailOf(detail.data, bookNames)
  const detailStatus = detailData?.trade?.status ?? null

  const [closing, setClosing] = useState(false)
  const [closeNote, setCloseNote] = useState(null)
  const stallTimer = useRef(null)

  useEffect(() => {
    if (!closing || detailStatus == null || detailStatus === 'ACTIVE') {
      return () => clearTimeout(stallTimer.current)
    }

    setClosing(false)
    setCloseNote(null)
    clearTimeout(stallTimer.current)

    return () => clearTimeout(stallTimer.current)
  }, [closing, detailStatus])

  async function closeTrade() {
    setCloseNote(null)
    setClosing(true)
    try {
      await apiPost(
        endpoints.tradeAction.submit,
        buildCloseTradeIntent(row.trade.id, row.valuation?.price),
      )
      stallTimer.current = setTimeout(() => {
        setCloseNote('Still waiting for confirmation — this can take a little longer under load.')
      }, CLOSE_STALL_MS)
    } catch {
      setClosing(false)
      setCloseNote('Close request failed — try again.')
    }
  }

  return (
    <TradeDetailDialog
      row={row}
      detail={detailData}
      auditEvents={normalizeAuditEvents(detail.data?.audit_logs)}
      loading={detail.loading}
      error={detail.error}
      lastUpdated={detail.lastUpdated}
      onClose={onClose}
      onCloseTrade={closeTrade}
      canClose={row.lifecycle === 'OPEN' && detailStatus === 'ACTIVE'}
      closing={closing}
      closeNote={closeNote}
    />
  )
}
