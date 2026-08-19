import StatusPill from '../status/StatusPill.jsx'
import Sparkline from '../charts/Sparkline.jsx'
import {
  formatAge,
  formatBidAsk,
  formatDelta,
  formatMarketSymbol,
  formatPercentDelta,
  formatTenor,
  formatValue,
  formatValueUnit,
} from '../../domain/marketFormat.js'
import { formatClockTime } from '../../domain/formatting.js'

function ChangeValue({ instrument, change }) {
  const percent = instrument.unit === 'rate' ? null : formatPercentDelta(change.percent)
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

export default function MarketCell({ column, row }) {
  const { instrument, observedChange, lastTickChange, live } = row

  switch (column.id) {
    case 'symbol':
      return formatMarketSymbol(instrument)
    case 'provider':
      return instrument.provider ?? '—'
    case 'tenor':
      return formatTenor(instrument.tenor)
    case 'assetClass':
      return (
        <span className="class-tag">
          <span className="class-tag__dot" />
          {instrument.assetClass}
        </span>
      )
    case 'marketLevel': {
      const unit = formatValueUnit(instrument)
      return (
        <span className="market-value">
          {formatValue(instrument)}
          {unit && <span className="market-value__unit">{unit}</span>}
        </span>
      )
    }
    case 'observedChange':
      return <ChangeValue instrument={instrument} change={observedChange} />
    case 'lastTickChange':
      return <ChangeValue instrument={instrument} change={lastTickChange} />
    case 'quote':
      return formatBidAsk(instrument)
    case 'trend':
      return <Sparkline values={instrument.history} />
    case 'age':
      return formatAge(row.providerAgeMs)
    case 'feed':
      return (
        <StatusPill level={live ? 'info' : 'stale'} label={live ? 'LIVE' : 'STALE'} compact />
      )
    case 'updated':
      return formatClockTime(instrument.eventTimeMs, { millis: true })
    default:
      return null
  }
}
