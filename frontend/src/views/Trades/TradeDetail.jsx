import { useEffect, useRef, useState } from 'react'
import { usePolling } from '../../hooks/usePolling.js'
import { apiGet, apiPost } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import { normalizeAuditEvents } from '../../domain/auditEvents.js'
import { tradeDetailOf } from '../../domain/trades.js'
import { buildCloseTradeIntent } from '../../domain/tradeActions.js'
import { describeApiError } from '../../domain/apiErrors.js'
import { curveOf } from '../../domain/curves.js'
import { BLOTTER_POLL_INTERVAL_MS } from '../../config/trades.js'
import TradeDetailPanel from '../../components/trades/TradeDetailPanel.jsx'

const CLOSE_STALL_MS = 15000
const MODEL_PRICED_CLASSES = new Set(['BOND', 'IRS', 'EUROPEAN_OPTION'])

export default function TradeDetail({ row, bookNames, instruments, curves, onClose }) {
  const detail = usePolling(
    ({ signal }) => apiGet(endpoints.blotter.trade(row.trade.id), { signal }),
    { intervalMs: BLOTTER_POLL_INTERVAL_MS },
  )
  const detailData = tradeDetailOf(detail.data, bookNames)
  const detailStatus = detailData?.trade?.status ?? null

  const [closing, setClosing] = useState(false)
  const [closeNote, setCloseNote] = useState(null)
  const [entryCurve, setEntryCurve] = useState(null)
  const [valuationCurve, setValuationCurve] = useState(null)
  const stallTimer = useRef(null)
  const modelPriced = MODEL_PRICED_CLASSES.has(row.trade.assetClass)
  const closingSide = row.trade.side === 'SELL' ? 'BUY' : 'SELL'
  const marketQuote = instruments?.[`${row.trade.provider}:${row.trade.symbol}`] ?? null
  const quotedClose = closingSide === 'BUY' ? marketQuote?.ask : marketQuote?.bid
  const closeReference = modelPriced
    ? row.valuation?.price
    : Number.isFinite(quotedClose)
      ? quotedClose
      : marketQuote?.value

  const curveName = row.trade.terms?.discount_curve
  const curveProvider = row.trade.terms?.discount_curve_provider
  const curveAsOf = row.trade.terms?.discount_curve_as_of
  const valuationCurveAsOf = row.valuation?.curveAsOf
  const feedCurve = curveName ? curves?.[curveName] ?? null : null

  useEffect(() => {
    if (row.trade.assetClass !== 'BOND' || !curveName || !curveProvider || !curveAsOf) return
    const controller = new AbortController()
    apiGet(
      endpoints.marketData.curveRevision(curveProvider, curveName, curveAsOf),
      { signal: controller.signal },
    )
      .then((data) => setEntryCurve(curveOf(data)))
      .catch(() => setEntryCurve(null))
    return () => controller.abort()
  }, [curveAsOf, curveName, curveProvider, row.trade.assetClass])

  useEffect(() => {
    if (
      row.trade.assetClass !== 'BOND' || !curveName || !curveProvider ||
      !valuationCurveAsOf || feedCurve?.asOfDate === valuationCurveAsOf
    ) {
      setValuationCurve(null)
      return
    }
    const controller = new AbortController()
    apiGet(
      endpoints.marketData.curveRevision(curveProvider, curveName, valuationCurveAsOf),
      { signal: controller.signal },
    )
      .then((data) => setValuationCurve(curveOf(data)))
      .catch(() => setValuationCurve(null))
    return () => controller.abort()
  }, [curveName, curveProvider, feedCurve?.asOfDate, row.trade.assetClass, valuationCurveAsOf])

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
        buildCloseTradeIntent(row.trade.id, closeReference),
      )
      stallTimer.current = setTimeout(() => {
        setCloseNote('Close pending — awaiting confirmation.')
      }, CLOSE_STALL_MS)
    } catch (err) {
      setClosing(false)
      setCloseNote(
        describeApiError(err, {
          service: 'Trade action service',
          outcome: 'the trade is still open.',
        }),
      )
    }
  }

  return (
    <TradeDetailPanel
      row={row}
      detail={detailData}
      entryCurve={entryCurve}
      currentCurve={feedCurve?.asOfDate === valuationCurveAsOf ? feedCurve : valuationCurve}
      auditEvents={normalizeAuditEvents(detail.data?.audit_logs)}
      loading={detail.loading}
      error={detail.error}
      lastUpdated={detail.lastUpdated}
      onClose={onClose}
      onCloseTrade={closeTrade}
      closeReference={closeReference}
      closeReferenceLabel={modelPriced ? 'Current model value' : `${closingSide} quote`}
      canClose={
        row.lifecycle === 'OPEN' &&
        detailStatus === 'ACTIVE' &&
        Number.isFinite(closeReference)
      }
      closing={closing}
      closeNote={closeNote}
    />
  )
}
