import StatusPill from '../status/StatusPill.jsx'
import { providerLabel } from '../../config/providers.js'
import {
  FRESHNESS_PILL_LEVELS,
  freshnessHintOf,
  freshnessLabelOf,
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
  const changePeriod = row.state === 'CLOSED' || instrument.marketOpen === false
    ? ' last session'
    : ' today'
  const closeLabel = row.state === 'CLOSED' || instrument.marketOpen === false
    ? 'PRIOR SESSION CLOSE'
    : 'PREVIOUS CLOSE'

  return (
    <section className="market-benchmark" aria-labelledby="market-benchmark-title">
      <div className="market-benchmark__head">
        <span className="market-benchmark__eyebrow">MARKET BENCHMARK</span>
        <StatusPill
          level={FRESHNESS_PILL_LEVELS[row.state] ?? 'unknown'}
          label={freshnessLabelOf(
            row.state,
            instrument.grade,
            instrument.providerTimestamp,
          )}
          title={freshnessHintOf(row.state, instrument.grade)}
          compact
        />
      </div>
      <div className="market-benchmark__hero">
        <div className="market-benchmark__identity">
          <h2 id="market-benchmark-title">{formatMarketSymbol(instrument)}</h2>
          <span>{providerLabel(instrument.provider)}</span>
        </div>
        <div className="market-benchmark__quote">
          <span className="market-benchmark__last">
            {formatUnitPrice(instrument.value, instrument.assetClass)}
          </span>
          <span className={`market-benchmark__today delta delta--${row.todayDirection}`}>
            {formatDelta(instrument, todayChange.delta)}
            {percent ? ` (${percent})` : ''}
            <span className="market-benchmark__today-label">{changePeriod}</span>
          </span>
        </div>
      </div>
      <dl className="market-benchmark__facts">
        <BenchmarkStat
          label={closeLabel}
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
    </section>
  )
}
