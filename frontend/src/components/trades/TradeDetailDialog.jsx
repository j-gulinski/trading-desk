import { useEffect, useRef, useState } from 'react'
import EmptyState from '../EmptyState.jsx'
import StatusPill from '../status/StatusPill.jsx'
import ValuationHistoryTable from './ValuationHistoryTable.jsx'
import { VALUATION_STATUS_LEVEL } from '../../config/valuations.js'
import {
  directionOf,
  formatAmount,
  formatClockTime,
  formatDateTime,
  formatSignedAmount,
  formatUnitPrice,
} from '../../domain/formatting.js'
import AuditEventList from '../audit/AuditEventList.jsx'

function DetailField({ label, children }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{children ?? '—'}</dd>
    </div>
  )
}

function CloseTradeControl({ canClose, closing, closeNote, onCloseTrade }) {
  const [confirming, setConfirming] = useState(false)

  if (!canClose) return null

  if (closing) {
    return (
      <span className="trade-detail__close-trade trade-detail__close-trade--pending">
        <span className="trade-detail__spinner" aria-hidden="true" />
        {closeNote ?? 'Closing…'}
      </span>
    )
  }

  return (
    <span className="trade-detail__close-trade">
      {closeNote && <span className="trade-detail__close-trade-error">{closeNote}</span>}
      {confirming ? (
        <>
          <span>Confirm close?</span>
          <button
            type="button"
            className="trade-detail__close-trade-confirm"
            onClick={() => {
              setConfirming(false)
              onCloseTrade()
            }}
          >
            Confirm
          </button>
          <button
            type="button"
            className="trade-detail__close-trade-cancel"
            onClick={() => setConfirming(false)}
          >
            Cancel
          </button>
        </>
      ) : (
        <button
          type="button"
          className="trade-detail__close-trade-button"
          onClick={() => setConfirming(true)}
        >
          Close trade
        </button>
      )}
    </span>
  )
}

function Metric({ label, value, tone = null, note }) {
  return (
    <div className="trade-detail__metric">
      <span className="trade-detail__metric-label">{label}</span>
      <strong className={tone ? `delta--${tone}` : undefined}>{value}</strong>
      <span className="trade-detail__metric-note">{note}</span>
    </div>
  )
}

export default function TradeDetailDialog({
  row,
  detail,
  auditEvents,
  loading,
  error,
  lastUpdated,
  onClose,
  onCloseTrade,
  canClose,
  closing,
  closeNote,
}) {
  const dialogRef = useRef(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog && !dialog.open) dialog.showModal()
  }, [])

  const trade = detail?.trade ?? row.trade
  const valuation = row.valuation
  const pnlLabel = row.lifecycle === 'OPEN' ? 'Unrealized PnL' : 'Realized PnL'

  return (
    <dialog
      ref={dialogRef}
      className="trade-detail"
      aria-labelledby="trade-detail-title"
      onClose={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) event.currentTarget.close()
      }}
    >
      <article className="trade-detail__surface">
        <header className="trade-detail__head">
          <div>
            <span className="trade-detail__eyebrow">TRADE DETAIL</span>
            <h2 id="trade-detail-title">{trade.tradeRef}</h2>
            <p>
              {trade.bookName} · {trade.symbol ?? 'UNKNOWN'} · {trade.assetClass}
            </p>
          </div>
          <div className="trade-detail__head-actions">
            <CloseTradeControl
              canClose={canClose}
              closing={closing}
              closeNote={closeNote}
              onCloseTrade={onCloseTrade}
            />
            <StatusPill
              level={VALUATION_STATUS_LEVEL[row.valuationStatus]}
              label={row.valuationStatus}
            />
            <button
              type="button"
              className="trade-detail__close"
              aria-label="Close trade details"
              autoFocus
              onClick={() => dialogRef.current?.close()}
            >
              ×
            </button>
          </div>
        </header>

        {error && (
          <div className="trade-detail__notice" role="status">
            Detail refresh failed — showing the last available data.
          </div>
        )}

        <div className="trade-detail__body">
          <section className="trade-detail__section" aria-labelledby="trade-summary-title">
            <div className="trade-detail__section-head">
              <h3 id="trade-summary-title">Trade</h3>
              <span>{trade.status}</span>
            </div>
            <dl className="trade-detail__fields">
              <DetailField label="Trade ID">{trade.id}</DetailField>
              <DetailField label="Book">{trade.bookName}</DetailField>
              <DetailField label="Instrument">{trade.symbol}</DetailField>
              <DetailField label="Class">{trade.assetClass}</DetailField>
              <DetailField label="Side">
                <span className={`trade-side trade-side--${trade.side.toLowerCase()}`}>
                  {trade.side}
                </span>
              </DetailField>
              <DetailField label="Quantity">{trade.quantity}</DetailField>
              <DetailField label="Entry">
                {formatUnitPrice(trade.entryPrice, trade.assetClass)}
              </DetailField>
              <DetailField label="Opened">{formatDateTime(trade.openedAtMs)}</DetailField>
              {row.lifecycle === 'CLOSED' && (
                <>
                  <DetailField label="Closed">{formatDateTime(trade.closedAtMs)}</DetailField>
                  <DetailField label="Close price">
                    {formatUnitPrice(trade.closePrice, trade.assetClass)}
                  </DetailField>
                  <DetailField label="Close reason">{trade.closeReason}</DetailField>
                </>
              )}
            </dl>
          </section>

          <section className="trade-detail__metrics" aria-label="Latest valuation">
            <Metric
              label="Fair value"
              value={formatAmount(valuation?.fairValue)}
              note={valuation?.currency ?? trade.currency ?? '—'}
            />
            <Metric
              label={pnlLabel}
              value={formatSignedAmount(row.pnl)}
              tone={directionOf(row.pnl)}
              note={valuation?.currency ?? trade.currency ?? '—'}
            />
            <Metric
              label="Valuation time"
              value={formatClockTime(valuation?.valuationTimeMs, { millis: true })}
              note={
                valuation == null
                  ? 'not valued yet'
                  : row.valuationSource === 'feed'
                    ? 'pricing stream'
                    : 'blotter snapshot'
              }
            />
          </section>

          <section className="trade-detail__section" aria-labelledby="valuation-history-title">
            <div className="trade-detail__section-head">
              <h3 id="valuation-history-title">Valuation history</h3>
              <span>
                {loading && !detail
                  ? 'LOADING'
                  : `${detail?.valuationHistory.length ?? 0} · newest first`}
              </span>
            </div>
            {loading && !detail && <EmptyState message="Loading valuation history…" />}
            {!loading && !detail && (
              <EmptyState message="Valuation history is unavailable." />
            )}
            {detail && detail.valuationHistory.length === 0 && (
              <EmptyState message="No persisted valuations for this trade yet." />
            )}
            {detail && detail.valuationHistory.length > 0 && (
              <ValuationHistoryTable valuations={detail.valuationHistory} />
            )}
          </section>

          <section className="trade-detail__section" aria-labelledby="trade-audit-title">
            <div className="trade-detail__section-head">
              <h3 id="trade-audit-title">Audit events</h3>
              <span>{auditEvents.length || (loading ? 'LOADING' : 0)}</span>
            </div>
            {loading && !detail && <EmptyState message="Loading trade audit events…" />}
            {!loading && auditEvents.length === 0 && (
              <EmptyState
                message={
                  error
                    ? 'Trade audit events are unavailable.'
                    : 'No audit events recorded for this trade.'
                }
              />
            )}
            {auditEvents.length > 0 && <AuditEventList events={auditEvents} />}
          </section>
        </div>

        <footer className="trade-detail__footer">
          <span>
            {lastUpdated == null
              ? 'Waiting for detail snapshot'
              : `Detail refreshed ${formatClockTime(lastUpdated)}`}
          </span>
          <span>Live value comes from the shared pricing feed</span>
        </footer>
      </article>
    </dialog>
  )
}
