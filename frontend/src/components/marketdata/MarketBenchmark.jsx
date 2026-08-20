import StatusPill from '../status/StatusPill.jsx'
import { providerLabel } from '../../config/providers.js'
import {
  FRESHNESS_LABELS,
  FRESHNESS_PILL_LEVELS,
} from '../../config/marketData.js'
import { formatUnitPrice } from '../../domain/formatting.js'
import {
  formatAge,
  formatDelta,
  formatMarketSymbol,
  formatPercentDelta,
} from '../../domain/marketFormat.js'

function BenchmarkStat({ label, value, className }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd className={className}>{value}</dd>
    </div>
  )
}

export default function MarketBenchmark({ row }) {
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
      <dl className="market-benchmark__stats">
        <BenchmarkStat
          label="LAST"
          value={formatUnitPrice(instrument.value, instrument.assetClass)}
        />
        <BenchmarkStat
          label="PREVIOUS CLOSE"
          value={formatUnitPrice(instrument.previousClose, instrument.assetClass)}
        />
        <BenchmarkStat
          label="CHANGE TODAY"
          className={`delta delta--${row.todayDirection}`}
          value={`${formatDelta(instrument, todayChange.delta)}${percent ? ` (${percent})` : ''}`}
        />
        <BenchmarkStat label="QUOTE AGE" value={formatAge(row.providerAgeMs)} />
      </dl>
      <StatusPill
        level={FRESHNESS_PILL_LEVELS[row.state] ?? 'unknown'}
        label={FRESHNESS_LABELS[row.state] ?? row.state}
        compact
      />
    </section>
  )
}
