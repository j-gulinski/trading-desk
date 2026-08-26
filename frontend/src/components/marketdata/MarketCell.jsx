import StatusPill from '../status/StatusPill.jsx'
import {
  formatAge,
  formatDelta,
  formatMarketSymbol,
  formatPercentDelta,
  marketLabelOf,
  unitLabelOf,
} from '../../domain/marketFormat.js'
import { formatClockTime, formatUnitPrice } from '../../domain/formatting.js'
import { providerLabel } from '../../config/providers.js'
import { assetClassLabel } from '../../config/tradeActions.js'
import {
  FRESHNESS_HINTS,
  FRESHNESS_LABELS,
  FRESHNESS_PILL_LEVELS,
} from '../../config/marketData.js'

function ChangeValue({ instrument, change }) {
  const percent = formatPercentDelta(change.percent)
  const currency = Number.isFinite(change.delta) ? instrument.currency : null
  return (
    <>
      <span>
        {formatDelta(instrument, change.delta)}
        {currency ? ` ${currency}` : ''}
      </span>
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
  const unit = Number.isFinite(instrument.value)
    ? unitLabelOf(instrument) ?? instrument.currency
    : null
  return (
    <span className="market-mark">
      <span className="market-mark__compact-provider">
        {providerLabel(instrument.provider)}
      </span>
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
  onRefresh,
  busyKey,
  refreshingKey,
  market,
}) {
  const { instrument, tickChange, todayChange } = row
  const strategy = strategies?.[instrument.provider]

  switch (column.id) {
    case 'symbol':
      return (
        <span className="market-symbol-stack">
          <span>{formatMarketSymbol(instrument)}</span>
          <span className="market-symbol-compact-meta">
            {instrument.held && (
              <span
                className="board-origin-tag"
                title="Used by an open position"
              >
                POS
              </span>
            )}
          </span>
        </span>
      )
    case 'name':
      return (
        <span className="market-instrument-name" title={instrument.name ?? undefined}>
          {instrument.name ?? '—'}
        </span>
      )
    case 'market':
      return (
        <span className="market-identity-value" title="Listing market or OTC market">
          {marketLabelOf({ ...instrument, market: market ?? instrument.market })}
        </span>
      )
    case 'provider':
      return instrument.provider ? providerLabel(instrument.provider) : '—'
    case 'assetClass':
      return (
        <span className="class-tag">
          <span className="class-tag__dot" />
          {assetClassLabel(instrument.assetClass)}
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
      if (instrument.watchlisted && (onRefresh || onRemove)) {
        const source = providerLabel(instrument.provider)
        const refreshLabel = `Refresh ${instrument.symbol} on ${source} now`
        const removeLabel = `Stop watching ${instrument.symbol} on ${source}`
        const refreshing = refreshingKey === instrument.id
        const mutating = busyKey === instrument.id
        return (
          <span className="watchlist-actions">
            {onRefresh && (
              <button
                type="button"
                className={`watchlist-action watchlist-action--refresh${refreshing ? ' is-refreshing' : ''}`}
                title={refreshLabel}
                aria-label={refreshLabel}
                aria-busy={refreshing || undefined}
                disabled={Boolean(refreshingKey) || mutating}
                onClick={(event) => {
                  event.stopPropagation()
                  onRefresh(instrument.symbol, instrument.provider)
                }}
              >
                <span aria-hidden="true">↻</span>
              </button>
            )}
            {onRemove && (
              <button
                type="button"
                className="watchlist-action watchlist-action--remove"
                title={removeLabel}
                aria-label={removeLabel}
                disabled={refreshing || mutating}
                onClick={(event) => {
                  event.stopPropagation()
                  onRemove(instrument.symbol, instrument.provider)
                }}
              >
                ✕
              </button>
            )}
          </span>
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
