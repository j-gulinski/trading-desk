import StatusPill from '../status/StatusPill.jsx'
import { providerLabel } from '../../config/providers.js'
import {
  FRESHNESS_PILL_LEVELS,
  freshnessHintOf,
  freshnessLabelOf,
} from '../../config/marketData.js'
import { formatUnitPrice } from '../../domain/formatting.js'
import { formatAsOfDate, formatMarketSymbol, unitLabelOf } from '../../domain/marketFormat.js'

const BPS_CHIP_PAIR = 'EURPLN'

function crossCheckBps(rows) {
  const mids = rows
    .filter((row) => row.instrument.symbol === BPS_CHIP_PAIR)
    .map((row) => ({ provider: row.instrument.provider, value: row.instrument.value }))
  if (mids.length < 2 || mids.some((entry) => !Number.isFinite(entry.value))) return null
  const [a, b] = mids
  const midpoint = (a.value + b.value) / 2
  if (midpoint === 0) return null
  return {
    providers: `${providerLabel(a.provider)} vs ${providerLabel(b.provider)}`,
    bps: (Math.abs(a.value - b.value) / midpoint) * 10000,
  }
}

function RateRow({ row, selected, onSelect }) {
  const { instrument, state } = row
  const unit = unitLabelOf(instrument)
  return (
    <li>
      <button
        type="button"
        className={`official-rates__row${selected ? ' official-rates__row--selected' : ''}`}
        onClick={() => onSelect(row)}
        title="Open fixing history and raw source data"
      >
        <span className="official-rates__pair">{formatMarketSymbol(instrument)}</span>
        <span className="official-rates__value">
          {formatUnitPrice(instrument.value, instrument.assetClass)}
          {unit && <span className="official-rates__unit">{unit}</span>}
        </span>
        <span className="official-rates__source">
          {providerLabel(instrument.provider)} · as of{' '}
          {formatAsOfDate(instrument.providerTimestampMs)}
        </span>
        <StatusPill
          level={FRESHNESS_PILL_LEVELS[state] ?? 'unknown'}
          label={freshnessLabelOf(state, instrument.grade)}
          title={freshnessHintOf(state, instrument.grade)}
          compact
        />
      </button>
    </li>
  )
}

export default function OfficialRates({ rows, selectedId, onSelect }) {
  if (rows.length === 0) return null
  const crossCheck = crossCheckBps(rows)

  return (
    <section className="official-rates" aria-labelledby="official-rates-title">
      <div className="official-rates__head">
        <span className="official-rates__eyebrow" id="official-rates-title">
          OFFICIAL RATES
        </span>
        {crossCheck && (
          <span
            className="official-rates__crosscheck"
            title={`EUR/PLN fixing difference between the two official sources (${crossCheck.providers})`}
          >
            EUR/PLN {crossCheck.providers} · {crossCheck.bps.toFixed(1)} bps
          </span>
        )}
      </div>
      <ul className="official-rates__list">
        {rows.map((row) => (
          <RateRow
            key={row.instrument.id}
            row={row}
            selected={row.instrument.id === selectedId}
            onSelect={onSelect}
          />
        ))}
      </ul>
    </section>
  )
}
