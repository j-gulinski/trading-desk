import StatusPill from '../status/StatusPill.jsx'
import {
  formatAge,
  formatDelta,
  formatMarketSymbol,
  formatPercentDelta,
  unitLabelOf,
} from '../../domain/marketFormat.js'
import { formatClockTime, formatUnitPrice } from '../../domain/formatting.js'
import { providerLabel } from '../../config/providers.js'
import {
  FRESHNESS_HINTS,
  FRESHNESS_LABELS,
  FRESHNESS_PILL_LEVELS,
} from '../../config/marketData.js'

function ChangeValue({ instrument, change }) {
  const percent = formatPercentDelta(change.percent)
  return (
    <>
      <span>{formatDelta(instrument, change.delta)}</span>
      {percent && (
        <>
          {' '}
          <span className="delta__percent">({percent})</span>
        </>
      )}
    </>
  )
}

function LastPrice({ instrument }) {
  const hasPreviousTick = Number.isFinite(instrument.previousValue)
  const className = hasPreviousTick
    ? `market-price-tick market-price-tick--${instrument.lastDirection}`
    : undefined
  const unit = unitLabelOf(instrument)
  return (
    <span className="market-mark">
      <span key={instrument.eventTimeMs ?? instrument.polledAtMs} className={className}>
        {formatUnitPrice(instrument.value, instrument.assetClass)}
      </span>
      {unit && <span className="market-mark__basis">{unit}</span>}
      {instrument.priceBasis && (
        <span className="market-mark__basis">{instrument.priceBasis.replaceAll('_', ' ')}</span>
      )}
    </span>
  )
}

function ageTitle(instrument, strategy) {
  const base = 'Time since the provider’s own quote event, not since the last poll'
  if (strategy?.next_batch_seconds == null) return base
  return `${base} · next ${providerLabel(instrument.provider)} batch in ${formatAge(
    strategy.next_batch_seconds * 1000,
  )}`
}

function feedTitle(state, instrument, strategy) {
  if (state === 'MISSING' && strategy?.next_batch_seconds != null) {
    const minutes = Math.max(1, Math.ceil(strategy.next_batch_seconds / 60))
    return `Waiting for the first quote — next ${providerLabel(
      instrument.provider,
    )} batch in ≤ ${minutes} min`
  }
  return FRESHNESS_HINTS[state]
}

export default function MarketCell({
  column,
  row,
  strategies,
  onRemove,
  busyKey,
}) {
  const { instrument, tickChange, todayChange } = row
  const strategy = strategies?.[instrument.provider]

  switch (column.id) {
    case 'symbol':
      return formatMarketSymbol(instrument)
    case 'provider':
      return instrument.provider ? providerLabel(instrument.provider) : '—'
    case 'assetClass':
      return (
        <span className="class-tag">
          <span className="class-tag__dot" />
          {instrument.assetClass}
        </span>
      )
    case 'last':
      return <LastPrice instrument={instrument} />
    case 'tickChange':
      return <ChangeValue instrument={instrument} change={tickChange} />
    case 'todayChange':
      return <ChangeValue instrument={instrument} change={todayChange} />
    case 'age':
      return <span title={ageTitle(instrument, strategy)}>{formatAge(row.providerAgeMs)}</span>
    case 'feed':
      return (
        <StatusPill
          level={FRESHNESS_PILL_LEVELS[row.state] ?? 'unknown'}
          label={FRESHNESS_LABELS[row.state] ?? row.state}
          title={feedTitle(row.state, instrument, strategy)}
          compact
        />
      )
    case 'watch':
      if (instrument.watchlisted && onRemove) {
        const label = `Stop watching ${instrument.symbol} on ${providerLabel(instrument.provider)}`
        return (
          <button
            type="button"
            className="watchlist-remove"
            title={label}
            aria-label={label}
            disabled={busyKey === instrument.id}
            onClick={(event) => {
              event.stopPropagation()
              onRemove(instrument.symbol, instrument.provider)
            }}
          >
            ✕
          </button>
        )
      }
      if (instrument.held) {
        return (
          <span
            className="board-origin-tag"
            title="Held in an open position — leaves the board when the position closes"
          >
            POS
          </span>
        )
      }
      if (instrument.benchmark) {
        return (
          <span className="board-origin-tag" title="Benchmark — always polled">
            BMK
          </span>
        )
      }
      return null
    case 'updated':
      return formatClockTime(instrument.polledAtMs, { millis: true })
    default:
      return null
  }
}
