import StatusPill from '../status/StatusPill.jsx'
import { providerLabel } from '../../config/providers.js'
import {
  FRESHNESS_HINTS,
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

const AGE_HINT =
  "Counts on the provider's last-trade clock — it keeps growing while the venue is closed"

function BenchmarkStat({ label, value, className, title }) {
  return (
    <div title={title}>
      <dt>{label}</dt>
      <dd className={className}>{value}</dd>
    </div>
  )
}

export default function MarketBenchmark({ row }) {
  if (!row) return null
  const { instrument, tickChange, todayChange } = row
  const percent = formatPercentDelta(todayChange.percent)

  return (
    <section className="market-benchmark" aria-labelledby="market-benchmark-title">
      <div className="market-benchmark__head">
        <span className="market-benchmark__eyebrow">MARKET BENCHMARK</span>
        <StatusPill
          level={FRESHNESS_PILL_LEVELS[row.state] ?? 'unknown'}
          label={FRESHNESS_LABELS[row.state] ?? row.state}
          title={FRESHNESS_HINTS[row.state]}
          compact
        />
      </div>
      <div className="market-benchmark__body">
        <div className="market-benchmark__identity">
          <h2 id="market-benchmark-title">{formatMarketSymbol(instrument)}</h2>
          <span>{providerLabel(instrument.provider)}</span>
        </div>
        <dl className="market-benchmark__stats">
          <BenchmarkStat
            label="LAST"
            className="market-benchmark__last"
            value={formatUnitPrice(instrument.value, instrument.assetClass)}
          />
          <BenchmarkStat
            label="CHANGE TODAY"
            className={`delta delta--${row.todayDirection}`}
            value={`${formatDelta(instrument, todayChange.delta)}${percent ? ` (${percent})` : ''}`}
          />
          <BenchmarkStat
            label="PREVIOUS CLOSE"
            value={formatUnitPrice(instrument.previousClose, instrument.assetClass)}
          />
          {Number.isFinite(tickChange.delta) && (
            <BenchmarkStat
              label="LAST TICK"
              className={`delta delta--${row.tickDirection}`}
              value={formatDelta(instrument, tickChange.delta)}
            />
          )}
          <BenchmarkStat
            label="QUOTE AGE"
            value={formatAge(row.providerAgeMs)}
            title={AGE_HINT}
          />
        </dl>
      </div>
    </section>
  )
}
