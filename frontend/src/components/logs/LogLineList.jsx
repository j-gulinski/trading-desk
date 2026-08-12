import StatusPill from '../status/StatusPill.jsx'
import LogPayload from './LogPayload.jsx'
import { formatClockTime } from '../../domain/formatting.js'
import { payloadEntriesOf } from '../../domain/logLines.js'

function LogRow({ line }) {
  return (
    <>
      <span className="audit-row__time">
        {formatClockTime(line.atMs, { millis: true, day: true })}
      </span>
      <StatusPill level={line.tone} label={line.level.toUpperCase()} compact />
      <span className="audit-row__service">{line.serviceLabel}</span>
      <span className="audit-row__message">{line.event}</span>
    </>
  )
}

export default function LogLineList({ lines, onCorrelationClick, onTradeClick, tail = false }) {
  return (
    <ul className={`audit-list log-list${tail ? ' log-list--tail' : ''}`}>
      {lines.map((line) => (
        <li key={line.id} className="audit-list__item">
          {payloadEntriesOf(line.payload).length === 0 ? (
            <div className="audit-row__summary audit-row__summary--static">
              <span className="audit-row__caret audit-row__caret--empty" aria-hidden="true" />
              <LogRow line={line} />
            </div>
          ) : (
            <details className="audit-row">
              <summary className="audit-row__summary">
                <span className="audit-row__caret" aria-hidden="true" />
                <LogRow line={line} />
              </summary>
              <div className="audit-row__detail">
                <LogPayload
                  payload={line.payload}
                  onTradeClick={onTradeClick}
                  onCorrelationClick={onCorrelationClick}
                />
              </div>
            </details>
          )}
        </li>
      ))}
    </ul>
  )
}
