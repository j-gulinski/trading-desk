import SidePanel from '../panel/SidePanel.jsx'
import Sparkline from '../charts/Sparkline.jsx'
import { providerLabel } from '../../config/providers.js'
import { formatClockTime, formatUnitPrice } from '../../domain/formatting.js'
import {
  formatDelta,
  formatMarketSymbol,
  formatPercentDelta,
} from '../../domain/marketFormat.js'

function Stat({ label, value }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}

export default function MarketTrendPanel({ row, onClose }) {
  const { instrument, todayChange } = row
  const points = instrument.history.filter(
    ([at, value]) => Number.isFinite(at) && Number.isFinite(value),
  )
  const values = points.map(([, value]) => value)
  const low = values.length > 0 ? Math.min(...values) : null
  const high = values.length > 0 ? Math.max(...values) : null
  const firstAt = points[0]?.[0]
  const lastAt = points.at(-1)?.[0]
  const percent = formatPercentDelta(todayChange.percent)

  return (
    <SidePanel
      eyebrow="INTRADAY QUOTE"
      title={formatMarketSymbol(instrument)}
      subtitle={`${providerLabel(instrument.provider)} · ${instrument.currency ?? '—'}`}
      wide
      onClose={onClose}
    >
      <section className="market-trend-detail" aria-label="Intraday price chart">
        <div className="market-trend-detail__chart">
          <Sparkline
            points={points}
            label="intraday accepted quotes"
            width={640}
            height={260}
          />
          <div className="market-trend-detail__axis">
            <span>{formatClockTime(firstAt)}</span>
            <span>{formatClockTime(lastAt)}</span>
          </div>
        </div>

        <dl className="market-trend-detail__stats">
          <Stat
            label="LAST"
            value={formatUnitPrice(instrument.value, instrument.assetClass)}
          />
          <Stat
            label="PREVIOUS CLOSE"
            value={formatUnitPrice(instrument.previousClose, instrument.assetClass)}
          />
          <Stat
            label="CHANGE TODAY"
            value={`${formatDelta(instrument, todayChange.delta)}${percent ? ` (${percent})` : ''}`}
          />
          <Stat label="OBSERVED LOW" value={formatUnitPrice(low, instrument.assetClass)} />
          <Stat label="OBSERVED HIGH" value={formatUnitPrice(high, instrument.assetClass)} />
          <Stat label="OBSERVATIONS" value={points.length} />
        </dl>

        <p className="market-trend-detail__note">
          The line contains accepted provider quotes from today at their real observation
          times. Previous close is a comparison value and is not plotted as an intraday
          observation.
        </p>

        {points.length > 0 && (
          <table className="market-trend-detail__observations">
            <caption>Latest observations</caption>
            <thead>
              <tr>
                <th>Time</th>
                <th>Price</th>
              </tr>
            </thead>
            <tbody>
              {points.slice(-12).reverse().map(([at, value]) => (
                <tr key={`${at}:${value}`}>
                  <td>{formatClockTime(at)}</td>
                  <td>{formatUnitPrice(value, instrument.assetClass)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </SidePanel>
  )
}
