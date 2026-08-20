import { useState } from 'react'
import EmptyState from '../EmptyState.jsx'
import StatusPill from '../status/StatusPill.jsx'
import SidePanel from '../panel/SidePanel.jsx'
import PanelTabs from '../panel/PanelTabs.jsx'
import ValuationHistoryTable from './ValuationHistoryTable.jsx'
import { VALUATION_STATUS_LABEL, VALUATION_STATUS_LEVEL } from '../../config/valuations.js'
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

export default function TradeDetailPanel({
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
  const [tab, setTab] = useState('details')

  const trade = detail?.trade ?? row.trade
  const valuation = row.valuation
  const pnlLabel = row.lifecycle === 'OPEN' ? 'Unrealized PnL' : 'Realized PnL'
  const historyCount = detail?.valuationHistory.length ?? null

  const tabs = [
    { id: 'details', label: 'Details' },
    { id: 'history', label: 'Valuation history', count: historyCount },
    { id: 'audit', label: 'Audit', count: auditEvents.length || null },
  ]

  return (
    <SidePanel
      wide
      eyebrow="TRADE DETAIL"
      title={trade.tradeRef}
      subtitle={`${trade.bookName} · ${trade.symbol ?? 'UNKNOWN'} · ${trade.assetClass}`}
      onClose={onClose}
      headActions={
        <>
          <CloseTradeControl
            canClose={canClose}
            closing={closing}
            closeNote={closeNote}
            onCloseTrade={onCloseTrade}
          />
          <StatusPill
            level={VALUATION_STATUS_LEVEL[row.valuationStatus]}
            label={VALUATION_STATUS_LABEL[row.valuationStatus] ?? row.valuationStatus}
          />
        </>
      }
      notice={
        error ? (
          <div className="side-panel__notice" role="status">
            Detail refresh failed — showing the last available data.
          </div>
        ) : null
      }
      tabs={
        <PanelTabs tabs={tabs} activeId={tab} onSelect={setTab} />
      }
      footer={
        <>
          <span>
            {lastUpdated == null
              ? 'Waiting for detail snapshot'
              : `Detail refreshed ${formatClockTime(lastUpdated)}`}
          </span>
          <span>Live value comes from the shared pricing feed</span>
        </>
      }
    >
      {tab === 'details' && (
        <div className="trade-detail__tabpanel">
          <section className="trade-detail__metrics">
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
              <DetailField label="Priced by">{trade.provider}</DetailField>
              <DetailField label="Quote time">
                {trade.entryPriceAtMs == null ? null : formatDateTime(trade.entryPriceAtMs)}
              </DetailField>
              <DetailField label="Opened">{formatDateTime(trade.openedAtMs)}</DetailField>
              {row.lifecycle === 'CLOSED' && (
                <>
                  <DetailField label="Closed">{formatDateTime(trade.closedAtMs)}</DetailField>
                  <DetailField label="Close price">
                    {formatUnitPrice(trade.closePrice, trade.assetClass)}
                  </DetailField>
                  <DetailField label="Close quote time">
                    {trade.closePriceAtMs == null ? null : formatDateTime(trade.closePriceAtMs)}
                  </DetailField>
                  <DetailField label="Close reason">{trade.closeReason}</DetailField>
                </>
              )}
            </dl>
          </section>
        </div>
      )}

      {tab === 'history' && (
        <div className="trade-detail__tabpanel">
          {loading && !detail && <EmptyState message="Loading valuation history…" />}
          {!loading && !detail && <EmptyState message="Valuation history is unavailable." />}
          {detail && detail.valuationHistory.length === 0 && (
            <EmptyState message="No persisted valuations for this trade yet." />
          )}
          {detail && detail.valuationHistory.length > 0 && (
            <ValuationHistoryTable valuations={detail.valuationHistory} />
          )}
        </div>
      )}

      {tab === 'audit' && (
        <div className="trade-detail__tabpanel">
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
        </div>
      )}
    </SidePanel>
  )
}
