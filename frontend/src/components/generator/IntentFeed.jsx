import StatusPill from '../status/StatusPill.jsx'
import { formatClockTime, formatShortId } from '../../domain/formatting.js'

export default function IntentFeed({ rows, showSource = false }) {
  return (
    <ul className="intent-feed">
      {rows.map((row) => (
        <li
          key={row.id}
          className={`intent-feed__row intent-feed__row--${row.direction.toLowerCase()}`}
        >
          <span className="intent-feed__time">{formatClockTime(row.atMs, { millis: true })}</span>
          <StatusPill level={row.tone} label={row.label} compact />
          <span className="intent-feed__trade">
            {row.tradeId ? formatShortId(row.tradeId) : '—'}
          </span>
          {showSource && <span className="intent-feed__source">{row.source}</span>}
          <span className="intent-feed__message">{row.message}</span>
        </li>
      ))}
    </ul>
  )
}
