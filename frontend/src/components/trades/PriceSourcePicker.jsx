import StatusPill from '../status/StatusPill.jsx'
import { providerLabel } from '../../config/providers.js'
import {
  FRESHNESS_HINTS,
  freshnessHintOf,
  freshnessLabelOf,
  freshnessPillLevelOf,
} from '../../config/marketData.js'

const NOT_OFFERED = new Set(['UNSUPPORTED', 'UNWATCHED'])

export default function PriceSourcePicker({
  label,
  quotes,
  selected,
  onSelect,
  children,
}) {
  const offered = quotes.filter((quote) => !NOT_OFFERED.has(quote.state))
  const notOffered = quotes.filter((quote) => NOT_OFFERED.has(quote.state))
  return (
    <div className="price-source">
      <span className="panel-form__label" id="new-trade-provider-label">{label}</span>
      {offered.length > 0 && (
        <div className="price-source__chips" role="radiogroup" aria-labelledby="new-trade-provider-label">
          {offered.map((quote) => (
            <button
              key={quote.provider}
              type="button"
              role="radio"
              className="price-source__chip"
              aria-checked={selected === quote.provider}
              disabled={!quote.tradeable}
              title={quote.reason ?? freshnessHintOf(quote.state, quote.grade) ?? FRESHNESS_HINTS[quote.state]}
              onClick={() => onSelect(quote.provider)}
            >
              <span className="price-source__chip-name">{providerLabel(quote.provider)}</span>
              <StatusPill
                level={freshnessPillLevelOf(quote.state, quote.grade)}
                label={freshnessLabelOf(quote.state, quote.grade, quote.providerTimestamp)}
                compact
              />
            </button>
          ))}
        </div>
      )}
      {notOffered.length > 0 && (
        <p className="price-source__note">
          {offered.length === 0 ? 'No source can price this: ' : 'Not offered: '}
          {notOffered
            .map((quote) => `${providerLabel(quote.provider)} (${quote.reason})`)
            .join(', ')}
        </p>
      )}
      {children}
    </div>
  )
}
