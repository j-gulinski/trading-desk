import Sparkline from '../charts/Sparkline.jsx'
import { isStale, lastTickChangeOf, observedChangeOf } from '../../domain/marketData.js'
import {
  directionOf,
  formatDelta,
  formatPercentDelta,
  formatValue,
} from '../../domain/marketFormat.js'

export default function MarketIndexCard({ instrument, now }) {
  const history = instrument?.history ?? []
  const session = instrument ? observedChangeOf(instrument) : null
  const lastTick = instrument ? lastTickChangeOf(instrument) : null
  const percent = formatPercentDelta(session?.percent)
  const summary = instrument
    ? `${formatDelta(instrument, session.delta)}${percent ? ` (${percent})` : ''} session · ${formatDelta(instrument, lastTick.delta)} last tick · ${isStale(instrument, now) ? 'STALE' : 'LIVE'}`
    : 'Awaiting benchmark'
  const direction = directionOf(session?.delta)
  const tone = direction === 'flat' ? 'default' : direction

  return (
    <article className={`stat-card stat-card--${tone} market-index-card`}>
      <div className="market-index-card__copy">
        <div className="stat-card__label">MARKET INDEX</div>
        <div className="stat-card__value">
          {instrument ? `${formatValue(instrument)} pts` : '—'}
        </div>
        <div className="stat-card__sub">{summary}</div>
      </div>
      <div className="market-index-card__trend">
        <Sparkline
          className="market-index-card__spark"
          values={history}
          width={260}
          height={72}
        />
        <span className="market-index-card__caption">
          {history.length > 1 ? `Last ${history.length} observations` : 'Building history…'}
        </span>
      </div>
    </article>
  )
}
