import { useState } from 'react'
import EmptyState from '../EmptyState.jsx'
import LoadingSkeleton from '../LoadingSkeleton.jsx'
import StatusPill from '../status/StatusPill.jsx'
import SidePanel from '../panel/SidePanel.jsx'
import PanelTabs from '../panel/PanelTabs.jsx'
import ValuationHistoryTable from './ValuationHistoryTable.jsx'
import { VALUATION_STATUS_LABEL, VALUATION_STATUS_LEVEL } from '../../config/valuations.js'
import { CURVE_ROLE_HINTS } from '../../config/marketData.js'
import { curveTitle } from '../../domain/curves.js'
import { providerLabel } from '../../config/providers.js'
import {
  directionOf,
  formatAmount,
  formatClockTime,
  formatDateTime,
  formatNumber,
  formatSignedAmount,
  formatUnitPrice,
} from '../../domain/formatting.js'
import AuditEventList from '../audit/AuditEventList.jsx'
import {
  tradePositionLabel,
  tradePriceForDisplay,
  tradeSize,
  tradeSizeLabel,
} from '../../domain/trades.js'
import { priceUnitLabelOf, quantityUnitLabelOf } from '../../domain/marketFormat.js'

const CURVE_TERMS = ['discount_curve', 'projection_curve']
const HIDDEN_TERMS = new Set([
  'asset_class',
  'currency',
  'direction',
  'face_value',
  'notional',
  'projection_curve_tracks_index',
])
const TERM_LABELS = {
  settlement_currency: 'Currency',
  face_value: 'Face amount',
  coupon_rate: 'Coupon',
  fixed_rate: 'Fixed rate',
  maturity_years: 'Maturity',
  payments_per_year: 'Payments / year',
  floating_rate_index_tenor: 'Floating index tenor',
  pricing_approach: 'Pricing approach',
  discount_curve: 'Discount curve',
  projection_curve: 'Projection curve',
  underlying_symbol: 'Underlying',
  option_type: 'Type',
  strike: 'Strike',
  multiplier: 'Contract multiplier',
  volatility: 'Volatility assumption',
  discount_curve_provider: 'Discount curve provider',
  discount_curve_as_of: 'Discount curve as of',
  projection_curve_provider: 'Projection curve provider',
  projection_curve_as_of: 'Projection curve as of',
  stale_curve_acknowledged: 'Stale curve acknowledged',
}
const TERM_ORDER = [
  'settlement_currency',
  'underlying_symbol',
  'option_type',
  'strike',
  'face_value',
  'coupon_rate',
  'fixed_rate',
  'maturity_years',
  'payments_per_year',
  'floating_rate_index_tenor',
  'pricing_approach',
  'multiplier',
  'volatility',
  'discount_curve',
  'discount_curve_provider',
  'discount_curve_as_of',
  'projection_curve',
  'projection_curve_provider',
  'projection_curve_as_of',
]
const TERM_RANK = new Map(TERM_ORDER.map((key, index) => [key, index]))

function visibleTermEntries(terms, assetClass) {
  return Object.entries(terms)
    .filter(([key, value]) => {
      if (HIDDEN_TERMS.has(key)) return false
      if (assetClass !== 'IRS') return true
      if (key === 'projection_curve') return value !== terms.discount_curve
      if (key === 'projection_curve_provider') {
        return value !== terms.discount_curve_provider
      }
      if (key === 'projection_curve_as_of') return value !== terms.discount_curve_as_of
      return true
    })
    .sort(([left], [right]) => (
      (TERM_RANK.get(left) ?? TERM_ORDER.length) -
      (TERM_RANK.get(right) ?? TERM_ORDER.length)
    ))
}

function termValueText(key, value) {
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  if (CURVE_TERMS.includes(key)) return curveTitle(String(value))
  if (key === 'pricing_approach' && value === 'SINGLE_CURVE_APPROXIMATION') {
    return 'Single-curve approximation'
  }
  if (key === 'coupon_rate' || key === 'fixed_rate') return `${formatNumber(value)}%`
  if (key === 'volatility') return `${formatNumber(Number(value) * 100)}%`
  if (key === 'maturity_years') {
    return `${formatNumber(value)} ${Number(value) === 1 ? 'year' : 'years'}`
  }
  if (typeof value === 'number') return formatNumber(value)
  return String(value)
}

function DetailField({ label, children }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{children ?? '—'}</dd>
    </div>
  )
}

function tradeValueLabel(trade, prefix) {
  if (trade.assetClass === 'BOND') return `${prefix} / 100 face`
  if (trade.assetClass === 'IRS') return `${prefix} NPV`
  if (trade.assetClass === 'EUROPEAN_OPTION') return `${prefix} premium / contract`
  if (trade.assetClass === 'FX') return `${prefix} rate`
  return `${prefix} price`
}

function tradeValueText(trade, value) {
  const display = tradePriceForDisplay(trade, value)
  const amount = trade.assetClass === 'IRS'
    ? formatSignedAmount(display)
    : formatUnitPrice(display, trade.assetClass)
  const unit = priceUnitLabelOf(trade)
  return amount === '—' || !unit ? amount : `${amount} ${unit}`
}

function tradeSizeText(trade) {
  const amount = formatNumber(tradeSize(trade))
  const unit = quantityUnitLabelOf(trade)
  return amount === '—' || !unit ? amount : `${amount} ${unit}`
}

function CloseTradeControl({
  canClose,
  closing,
  closeNote,
  indicativeValue,
  closeReference,
  closeReferenceLabel,
  currency,
  source,
  valuationTimeMs,
  onCloseTrade,
}) {
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
        <span className="trade-detail__close-confirmation" role="dialog" aria-label="Confirm trade close">
          <strong>Close at current market?</strong>
          <span>
            {Number.isFinite(indicativeValue)
              ? `${formatAmount(indicativeValue)} ${currency ?? ''}`.trim()
              : 'Indicative position value unavailable'}
          </span>
          <small>
            {source ?? 'Current valuation'}
            {valuationTimeMs != null ? ` · ${formatClockTime(valuationTimeMs)}` : ''}
          </small>
          <small>
            {closeReferenceLabel}: {Number.isFinite(closeReference)
              ? `${formatAmount(closeReference)} ${currency ?? ''}`.trim()
              : 'unavailable'}
          </small>
          <small>Final close value is recomputed from current market data.</small>
          <span className="trade-detail__close-confirmation-actions">
            <button
              type="button"
              className="trade-detail__close-trade-confirm"
              onClick={() => {
                setConfirming(false)
                onCloseTrade()
              }}
            >
              Confirm close
            </button>
            <button
              type="button"
              className="trade-detail__close-trade-cancel"
              onClick={() => setConfirming(false)}
            >
              Cancel
            </button>
          </span>
        </span>
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
  closeReference,
  closeReferenceLabel,
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
            indicativeValue={valuation?.fairValue}
            closeReference={closeReference}
            closeReferenceLabel={closeReferenceLabel}
            currency={valuation?.currency ?? trade.currency}
            source={trade.provider || valuation?.marketDataProvider
              ? providerLabel(trade.provider ?? valuation.marketDataProvider)
              : 'Model source unavailable'}
            valuationTimeMs={valuation?.valuationTimeMs}
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
        <span>
          {lastUpdated == null
            ? 'Waiting for detail'
            : `Updated ${formatClockTime(lastUpdated)}`}
        </span>
      }
    >
      {tab === 'details' && (
        <div className="trade-detail__tabpanel">
          <section className="trade-detail__metrics">
            <Metric
              label="Position value"
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
                    ? 'live'
                    : 'latest'
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
              <DetailField label={trade.assetClass === 'IRS' ? 'Direction' : 'Side'}>
                <span className={`trade-side trade-side--${trade.side.toLowerCase()}`}>
                  {tradePositionLabel(trade)}
                </span>
              </DetailField>
              <DetailField label={tradeSizeLabel(trade)}>{tradeSizeText(trade)}</DetailField>
              <DetailField label={tradeValueLabel(trade, 'Entry')}>
                {tradeValueText(trade, trade.entryPrice)}
              </DetailField>
              <DetailField label="Pricing source">
                {trade.provider || valuation?.marketDataProvider
                  ? providerLabel(trade.provider ?? valuation.marketDataProvider)
                  : null}
              </DetailField>
              <DetailField label={['BOND', 'IRS'].includes(trade.assetClass) ? 'Curve as of' : 'Quote time'}>
                {trade.entryPriceAtMs == null ? null : formatDateTime(trade.entryPriceAtMs)}
              </DetailField>
              <DetailField label="Opened">{formatDateTime(trade.openedAtMs)}</DetailField>
              <DetailField label="Source">{trade.source}</DetailField>
              <DetailField label="Written by">{trade.createdByService}</DetailField>
              {trade.terms != null &&
                Object.keys(trade.terms).some(
                  (key) => !HIDDEN_TERMS.has(key),
                ) && (
                <DetailField label="Terms">
                  <dl className="trade-detail__terms">
                    {visibleTermEntries(trade.terms, trade.assetClass)
                      .map(([key, value]) => (
                        <div key={key}>
                          <dt
                            className={
                              CURVE_ROLE_HINTS[key] ? 'trade-detail__terms-hinted' : undefined
                            }
                            title={CURVE_ROLE_HINTS[key]}
                          >
                            {key === 'discount_curve' && trade.assetClass === 'IRS'
                              ? 'Discount / projection curve'
                              : TERM_LABELS[key] ?? key.replaceAll('_', ' ')}
                          </dt>
                          <dd>{termValueText(key, value)}</dd>
                        </div>
                      ))}
                  </dl>
                </DetailField>
              )}
              {row.lifecycle === 'CLOSED' && (
                <>
                  <DetailField label="Closed">{formatDateTime(trade.closedAtMs)}</DetailField>
                  <DetailField label={tradeValueLabel(trade, 'Close')}>
                    {tradeValueText(trade, trade.closePrice)}
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
          {loading && !detail && (
            <LoadingSkeleton variant="table" label="Loading valuation history" />
          )}
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
          {loading && !detail && (
            <LoadingSkeleton variant="list" label="Loading trade audit events" />
          )}
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
