import Sparkline from '../charts/Sparkline.jsx'
import StatusPill from '../status/StatusPill.jsx'
import { providerLabel } from '../../config/providers.js'
import {
  FRESHNESS_LABELS,
  FRESHNESS_PILL_LEVELS,
} from '../../config/marketData.js'
import { formatUnitPrice } from '../../domain/formatting.js'
import {
  formatDelta,
  formatMarketSymbol,
  formatPercentDelta,
} from '../../domain/marketFormat.js'

export default function MarketBenchmark({ row, onInspect }) {
  if (!row) return null
  const { instrument, todayChange } = row
  const percent = formatPercentDelta(todayChange.percent)

  return (
    <section className="market-benchmark" aria-labelledby="market-benchmark-title">
      <div className="market-benchmark__identity">
        <span className="market-benchmark__eyebrow">MARKET BENCHMARK</span>
        <h2 id="market-benchmark-title">{formatMarketSymbol(instrument)}</h2>
        <span>{providerLabel(instrument.provider)}</span>
      </div>
      <div className={`market-benchmark__change delta delta--${row.todayDirection}`}>
        <strong>{formatUnitPrice(instrument.value, instrument.assetClass)}</strong>
        <span>
          {formatDelta(instrument, todayChange.delta)}{percent ? ` (${percent})` : ''}
        </span>
      </div>
      <button
        type="button"
        className="market-benchmark__chart"
        onClick={() => onInspect(row)}
        title="View benchmark intraday details"
      >
        <Sparkline points={instrument.history} label="benchmark intraday" width={180} height={44} />
      </button>
      <StatusPill
        level={FRESHNESS_PILL_LEVELS[row.state] ?? 'unknown'}
        label={FRESHNESS_LABELS[row.state] ?? row.state}
        compact
      />
      <button type="button" className="market-benchmark__view" onClick={() => onInspect(row)}>
        View chart →
      </button>
    </section>
  )
}
