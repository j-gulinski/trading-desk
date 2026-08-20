import StatusPill from '../status/StatusPill.jsx'
import Sparkline from '../charts/Sparkline.jsx'
import {
  formatAge,
  formatDelta,
  formatMarketSymbol,
  formatPercentDelta,
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

export default function MarketCell({
  column,
  row,
  historyLabel,
  onInspect,
  onRemove,
  busyKey,
}) {
  const { instrument, todayChange } = row

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
      return formatUnitPrice(instrument.last, instrument.assetClass)
    case 'todayChange':
      return <ChangeValue instrument={instrument} change={todayChange} />
    case 'trend':
      return (
        <button
          type="button"
          className="market-trend-button"
          title={`View ${instrument.symbol} intraday details`}
          onClick={() => onInspect?.(row)}
        >
          <Sparkline points={instrument.history} label={historyLabel} />
        </button>
      )
    case 'age':
      return formatAge(row.providerAgeMs)
    case 'feed':
      return (
        <StatusPill
          level={FRESHNESS_PILL_LEVELS[row.state] ?? 'unknown'}
          label={FRESHNESS_LABELS[row.state] ?? row.state}
          title={FRESHNESS_HINTS[row.state]}
          compact
        />
      )
    case 'watch':
      if (instrument.watchlisted && onRemove) {
        const label = `Stop watching ${instrument.symbol} on ${instrument.provider}`
        return (
          <button
            type="button"
            className="watchlist-remove"
            title={label}
            aria-label={label}
            disabled={busyKey === instrument.id}
            onClick={() => onRemove(instrument.symbol, instrument.provider)}
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
