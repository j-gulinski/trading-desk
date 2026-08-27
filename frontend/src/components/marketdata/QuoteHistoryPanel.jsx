import { useEffect, useState } from 'react'
import SidePanel from '../panel/SidePanel.jsx'
import StatusPill from '../status/StatusPill.jsx'
import EmptyState from '../EmptyState.jsx'
import LoadingSkeleton from '../LoadingSkeleton.jsx'
import { useQuoteHistory } from '../../hooks/useQuoteHistory.js'
import {
  formatAge,
  formatAsOfDate,
  formatDelta,
  formatMarketSymbol,
  formatPercentDelta,
  unitLabelOf,
} from '../../domain/marketFormat.js'
import {
  directionOf,
  formatClockTime,
  formatUnitPrice,
} from '../../domain/formatting.js'
import { providerLabel } from '../../config/providers.js'
import {
  freshnessPillLevelOf,
  freshnessHintOf,
  freshnessLabelOf,
} from '../../config/marketData.js'
import { toNum as toNumber, toTime } from '../../domain/values.js'

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
    rawPayload: item.raw_payload ?? null,
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

function HistoryItem({ point, previous, instrument, reference }) {
  const change = changeFrom(point, previous)
  const tone = directionOf(change.delta)
  const eventTime = point.providerTimestampMs ?? point.receivedAtMs
  return (
    <li className={`quote-history__tick quote-history__tick--${tone}`}>
      <span className="quote-history__rail" aria-hidden="true" />
      <div className="quote-history__tick-head">
        <time dateTime={eventTime ? new Date(eventTime).toISOString() : undefined}>
          {reference
            ? `as of ${formatAsOfDate(point.providerTimestampMs)}`
            : `provider ${formatClockTime(eventTime, { day: true })}`}
        </time>
      </div>
      <div className="quote-history__tick-main">
        <strong>{formatUnitPrice(point.mark, instrument.assetClass)}</strong>
        <Change instrument={instrument} {...change} />
      </div>
      {!reference && (
        <div className="quote-history__tick-market">
          {Number.isFinite(point.bid) && (
            <span>BID {formatUnitPrice(point.bid, instrument.assetClass)}</span>
          )}
          {Number.isFinite(point.ask) && (
            <span>ASK {formatUnitPrice(point.ask, instrument.assetClass)}</span>
          )}
          {Number.isFinite(point.last) && (
            <span>LAST {formatUnitPrice(point.last, instrument.assetClass)}</span>
          )}
        </div>
      )}
      <div className="quote-history__tick-meta">
        {!reference && <span>{basisLabel(point.priceBasis)}</span>}
        <span>received {formatClockTime(point.receivedAtMs, { millis: true })}</span>
      </div>
    </li>
  )
}

const INITIAL_HISTORY_ROWS = 15
const HISTORY_PAGE_ROWS = 15

export default function QuoteHistoryPanel({ row, onClose }) {
  const { instrument, state, tickChange, todayChange, providerAgeMs } = row
  const history = useQuoteHistory(instrument)
  const points = normalizeHistory(history.rows)
  const symbol = formatMarketSymbol(instrument)
  const currentTone = directionOf(tickChange.delta)
  const reference = instrument.grade === 'REFERENCE'
  const changePeriod = state === 'CLOSED' || instrument.marketOpen === false
    ? 'LAST SESSION'
    : 'TODAY'
  const unit = unitLabelOf(instrument)
  const latestRawPayload = points.find((point) => point.rawPayload != null)?.rawPayload ?? null
  const marketMetricCount = [instrument.bid, instrument.ask, instrument.last]
    .filter(Number.isFinite).length
  const metricCount = reference ? 3 : marketMetricCount + 3
  const emptyMetricCount = (3 - metricCount % 3) % 3
  const [visibleRows, setVisibleRows] = useState(INITIAL_HISTORY_ROWS)
  useEffect(() => {
    setVisibleRows(INITIAL_HISTORY_ROWS)
  }, [instrument.provider, instrument.symbol])
  const visiblePoints = points.slice(0, visibleRows)

  return (
    <SidePanel
      eyebrow="QUOTE DETAIL"
      title={symbol}
      subtitle={`${providerLabel(instrument.provider)} · ${instrument.assetClass} · ${unit ?? instrument.currency ?? '—'}`}
      bodyClassName="quote-history-panel"
      onClose={onClose}
      headActions={
        <StatusPill
          level={freshnessPillLevelOf(state, instrument.grade)}
          label={freshnessLabelOf(state, instrument.grade, instrument.providerTimestamp)}
          title={freshnessHintOf(state, instrument.grade)}
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
              {instrument.currency && (
                <span className="quote-history__current-currency">{instrument.currency}</span>
              )}
            </strong>
          </div>
          <div className="quote-history__current-moves">
            <span>LAST TICK</span>
            <Change instrument={instrument} {...tickChange} empty="waiting for next tick" />
            <span>{changePeriod}</span>
            <Change instrument={instrument} {...todayChange} empty="no previous close" />
          </div>
        </div>

        <dl className="quote-history__metrics">
          {!reference && Number.isFinite(instrument.bid) && (
            <Metric label="Bid" value={formatUnitPrice(instrument.bid, instrument.assetClass)} />
          )}
          {!reference && Number.isFinite(instrument.ask) && (
            <Metric label="Ask" value={formatUnitPrice(instrument.ask, instrument.assetClass)} />
          )}
          {!reference && Number.isFinite(instrument.last) && (
            <Metric label="Last" value={formatUnitPrice(instrument.last, instrument.assetClass)} />
          )}
          <Metric label="Basis" value={basisLabel(instrument.priceBasis)} note={instrument.grade} />
          <Metric
            label={reference ? 'As of' : 'Provider time'}
            value={
              reference
                ? formatAsOfDate(instrument.providerTimestampMs)
                : formatClockTime(instrument.providerTimestampMs, { millis: true })
            }
            note={reference ? 'official fixing date' : `${formatAge(providerAgeMs)} · local time`}
          />
          <Metric
            label="Received"
            value={formatClockTime(instrument.polledAtMs, { millis: true })}
            note="local time"
          />
          {Array.from({ length: emptyMetricCount }, (_, index) => (
            <div
              key={`empty-metric-${index}`}
              className="quote-history__metric quote-history__metric--empty"
              aria-hidden="true"
            />
          ))}
        </dl>
      </section>

      <section className="quote-history__observations" aria-labelledby="observed-history-title">
        <header className="quote-history__section-head">
          <div>
            <h3 id="observed-history-title">Observed price changes</h3>
            <p>Newest first · showing {Math.min(visibleRows, points.length)} of {points.length}</p>
          </div>
        </header>

        <div
          className="quote-history__tape"
          tabIndex={0}
          aria-label="Observed quote changes"
        >
          {history.loading ? (
            <LoadingSkeleton variant="panel" label="Loading observed quote changes" />
          ) : points.length === 0 ? (
            <EmptyState message="No stored price changes for this provider-symbol yet." />
          ) : (
            <ol className="quote-history__ticks">
              {visiblePoints.map((point, index) => (
                <HistoryItem
                  key={point.id}
                  point={point}
                  previous={points[index + 1]}
                  instrument={instrument}
                  reference={reference}
                />
              ))}
            </ol>
          )}
        </div>
        {visibleRows < points.length && (
          <button
            type="button"
            className="quote-history__more"
            onClick={() => setVisibleRows((current) => current + HISTORY_PAGE_ROWS)}
          >
            Show 15 older observations
          </button>
        )}
        {latestRawPayload != null && (
          <details className="quote-history__raw">
            <summary>Latest raw source response</summary>
            <pre>{JSON.stringify(latestRawPayload, null, 2)}</pre>
          </details>
        )}
      </section>
    </SidePanel>
  )
}
