import StatusPill from '../status/StatusPill.jsx'
import { providerLabel } from '../../config/providers.js'
import {
  FRESHNESS_HINTS,
  FRESHNESS_LABELS,
  FRESHNESS_PILL_LEVELS,
} from '../../config/marketData.js'
import { formatClockTime, formatUnitPrice } from '../../domain/formatting.js'
import { formatAge } from '../../domain/marketFormat.js'

const UNAVAILABLE_LABELS = {
  UNSUPPORTED: 'N/A',
  UNWATCHED: 'NOT WATCHED',
}

function QuoteLeg({ label, value, assetClass, filled }) {
  return (
    <span className={`quote-leg${filled ? ' quote-leg--filled' : ''}`}>
      <span className="quote-leg__label">{label}</span>
      {Number.isFinite(value) ? formatUnitPrice(value, assetClass) : '—'}
    </span>
  )
}

export default function ProviderQuoteOption({
  quote,
  assetClass,
  side,
  selected,
  now,
  onSelect,
}) {
  const unavailable = UNAVAILABLE_LABELS[quote.state]
  return (
    <li className="quote-option">
      <button
        type="button"
        className="quote-option__button"
        aria-pressed={selected}
        disabled={!Number.isFinite(quote.price)}
        title={quote.reason ?? FRESHNESS_HINTS[quote.state]}
        onClick={() => onSelect(quote.provider)}
      >
        <span className="quote-option__provider">{providerLabel(quote.provider)}</span>
        <StatusPill
          level={unavailable ? 'unknown' : (FRESHNESS_PILL_LEVELS[quote.state] ?? 'unknown')}
          label={unavailable ?? FRESHNESS_LABELS[quote.state] ?? quote.state}
          compact
        />
        {quote.reason ? (
          <span className="quote-option__meta">{quote.reason}</span>
        ) : (
          <>
            <span className="quote-option__legs">
              <QuoteLeg
                label="bid"
                value={quote.bid}
                assetClass={assetClass}
                filled={side === 'SELL' && Number.isFinite(quote.bid)}
              />
              <QuoteLeg
                label="ask"
                value={quote.ask}
                assetClass={assetClass}
                filled={side === 'BUY' && Number.isFinite(quote.ask)}
              />
              <QuoteLeg
                label="last"
                value={quote.last}
                assetClass={assetClass}
                filled={!Number.isFinite(quote.bid) && !Number.isFinite(quote.ask)}
              />
            </span>
            <span className="quote-option__meta">
              {quote.atMs != null
                ? `${formatClockTime(quote.atMs)} · ${formatAge(now - quote.atMs)} old`
                : 'Timestamp unavailable'}
            </span>
          </>
        )}
      </button>
    </li>
  )
}
