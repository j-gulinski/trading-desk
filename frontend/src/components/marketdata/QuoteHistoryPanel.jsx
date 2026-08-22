import SidePanel from '../panel/SidePanel.jsx'
import StatusPill from '../status/StatusPill.jsx'
import EmptyState from '../EmptyState.jsx'
import { useQuoteHistory } from '../../hooks/useQuoteHistory.js'
import {
  formatAge,
  formatDelta,
  formatMarketSymbol,
  formatPercentDelta,
} from '../../domain/marketFormat.js'
import { directionOf, formatClockTime, formatUnitPrice } from '../../domain/formatting.js'
import { providerLabel } from '../../config/providers.js'
import {
  FRESHNESS_HINTS,
  FRESHNESS_LABELS,
  FRESHNESS_PILL_LEVELS,
} from '../../config/marketData.js'

function toNumber(value) {
  if (value == null || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function toTime(value) {
  const parsed = Date.parse(value ?? '')
  return Number.isFinite(parsed) ? parsed : null
}

function basisLabel(value) {
  return value ? value.replaceAll('_', ' ') : '—'
}

function Metric({ label, value, note }) {
  return (
    <div className="quote-history__metric">
      <dt>{label}</dt>
      <dd>{value}</dd>
      {note && <span>{note}</span>}
    </div>
  )
}

function Change({ instrument, delta, percent, empty = 'first observed value' }) {
  if (!Number.isFinite(delta)) return <span className="quote-history__change--empty">{empty}</span>
  const tone = directionOf(delta)
  return (
    <span className={`quote-history__change delta delta--${tone}`}>
      {formatDelta(instrument, delta)}
      <span>{formatPercentDelta(percent)}</span>
    </span>
  )
}

function normalizeHistory(rows) {
  return rows.map((item) => ({
    id: item.snapshot_id,
    assetClass: item.asset_class,
    currency: item.currency,
    bid: toNumber(item.bid),
    ask: toNumber(item.ask),
    last: toNumber(item.last),
    mark: toNumber(item.mid),
    priceBasis: item.price_basis,
    providerTimestampMs: toTime(item.provider_timestamp),
    receivedAtMs: toTime(item.received_at),
  }))
}

function changeFrom(point, previous) {
  if (!Number.isFinite(point.mark) || !Number.isFinite(previous?.mark)) {
    return { delta: null, percent: null }
  }
  const delta = point.mark - previous.mark
  return {
    delta,
    percent: previous.mark === 0 ? null : (delta / Math.abs(previous.mark)) * 100,
  }
}

function HistoryItem({ point, previous, instrument }) {
  const change = changeFrom(point, previous)
  const tone = directionOf(change.delta)
  const eventTime = point.providerTimestampMs ?? point.receivedAtMs
  return (
    <li className={`quote-history__tick quote-history__tick--${tone}`}>
      <span className="quote-history__rail" aria-hidden="true" />
      <div className="quote-history__tick-head">
        <time dateTime={eventTime ? new Date(eventTime).toISOString() : undefined}>
          provider {formatClockTime(eventTime, { day: true })}
        </time>
      </div>
      <div className="quote-history__tick-main">
        <strong>{formatUnitPrice(point.mark, instrument.assetClass)}</strong>
        <Change instrument={instrument} {...change} />
      </div>
      <div className="quote-history__tick-market">
        <span>BID {formatUnitPrice(point.bid, instrument.assetClass)}</span>
        <span>ASK {formatUnitPrice(point.ask, instrument.assetClass)}</span>
        <span>LAST {formatUnitPrice(point.last, instrument.assetClass)}</span>
      </div>
      <div className="quote-history__tick-meta">
        <span>{basisLabel(point.priceBasis)}</span>
        <span>received {formatClockTime(point.receivedAtMs, { millis: true })}</span>
      </div>
    </li>
  )
}

export default function QuoteHistoryPanel({ row, onClose }) {
  const { instrument, state, tickChange, todayChange, providerAgeMs } = row
  const history = useQuoteHistory(instrument)
  const points = normalizeHistory(history.rows)
  const symbol = formatMarketSymbol(instrument)
  const currentTone = directionOf(tickChange.delta)

  return (
    <SidePanel
      eyebrow="QUOTE DETAIL"
      title={symbol}
      subtitle={`${providerLabel(instrument.provider)} · ${instrument.assetClass} · ${instrument.currency ?? '—'}`}
      bodyClassName="quote-history-panel"
      onClose={onClose}
      headActions={
        <StatusPill
          level={FRESHNESS_PILL_LEVELS[state] ?? 'unknown'}
          label={FRESHNESS_LABELS[state] ?? state}
          title={FRESHNESS_HINTS[state]}
        />
      }
      notice={
        history.error ? (
          <div className="side-panel__notice" role="status">
            {history.error} — showing the live quote only.
          </div>
        ) : null
      }
    >
      <section className="quote-history__current" aria-labelledby="current-quote-title">
        <div className="quote-history__current-head">
          <div>
            <span id="current-quote-title">CURRENT MARK</span>
            <strong className={`quote-history__current-price quote-history__current-price--${currentTone}`}>
              {formatUnitPrice(instrument.value, instrument.assetClass)}
            </strong>
          </div>
          <div className="quote-history__current-moves">
            <span>LAST TICK</span>
            <Change instrument={instrument} {...tickChange} empty="waiting for next tick" />
            <span>TODAY</span>
            <Change instrument={instrument} {...todayChange} empty="no previous close" />
          </div>
        </div>

        <dl className="quote-history__metrics">
          <Metric label="Bid" value={formatUnitPrice(instrument.bid, instrument.assetClass)} />
          <Metric label="Ask" value={formatUnitPrice(instrument.ask, instrument.assetClass)} />
          <Metric label="Last" value={formatUnitPrice(instrument.last, instrument.assetClass)} />
          <Metric label="Basis" value={basisLabel(instrument.priceBasis)} note={instrument.grade} />
          <Metric
            label="Provider time"
            value={formatClockTime(instrument.providerTimestampMs, { millis: true })}
            note={formatAge(providerAgeMs)}
          />
          <Metric
            label="Received"
            value={formatClockTime(instrument.polledAtMs, { millis: true })}
          />
        </dl>
      </section>

      <section className="quote-history__observations" aria-labelledby="observed-history-title">
        <header className="quote-history__section-head">
          <div>
            <h3 id="observed-history-title">Observed price changes</h3>
            <p>Newest first</p>
          </div>
        </header>

        <div
          className="quote-history__tape"
          tabIndex={0}
          aria-label="Observed quote changes"
        >
          {history.loading ? (
            <EmptyState message="Loading observed quote changes…" />
          ) : points.length === 0 ? (
            <EmptyState message="No stored price changes for this provider-symbol yet." />
          ) : (
            <ol className="quote-history__ticks">
              {points.map((point, index) => (
                <HistoryItem
                  key={point.id}
                  point={point}
                  previous={points[index + 1]}
                  instrument={instrument}
                />
              ))}
            </ol>
          )}
        </div>
      </section>
    </SidePanel>
  )
}
