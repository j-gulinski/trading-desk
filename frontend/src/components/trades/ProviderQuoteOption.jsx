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

export default function ProviderQuoteOption({
  quote,
  assetClass,
  unit,
  side,
  selected,
  now,
  onSelect,
}) {
  const unavailable = UNAVAILABLE_LABELS[quote.state]
  const priceUnit = unit ?? quote.currency
  return (
    <li className="quote-option">
      <button
        type="button"
        className="quote-option__button"
        aria-pressed={selected}
        disabled={!quote.tradeable}
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
            <span className="quote-option__price">
              {side == null ? 'underlying mark' : `${side === 'BUY' ? 'buy' : 'sell'} at`}{' '}
              {formatUnitPrice(quote.price, assetClass)}
              {priceUnit ? ` ${priceUnit}` : ''}
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
