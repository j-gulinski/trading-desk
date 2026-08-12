import StatusPill from '../status/StatusPill.jsx'
import { formatClockTime } from '../../domain/formatting.js'

export default function AuditEventList({ events, onCorrelationClick }) {
  return (
    <ul className="audit-list">
      {events.map((event) => (
        <li key={event.id} className="audit-list__item">
          <details className="audit-row">
            <summary className="audit-row__summary">
              <span className="audit-row__caret" aria-hidden="true" />
              <span className="audit-row__time">{formatClockTime(event.createdAtMs)}</span>
              <StatusPill level={event.tone} label={event.severity} />
              <span className="audit-row__service">{event.serviceLabel}</span>
              <span className="audit-row__message">{event.message}</span>
            </summary>
            <div className="audit-row__detail">
              <p className="audit-row__detail-message">{event.message}</p>
              <dl className="audit-row__meta-grid">
                <div>
                  <dt>Event</dt>
                  <dd>{event.eventType}</dd>
                </div>
                <div>
                  <dt>Service</dt>
                  <dd>{event.service ?? '—'}</dd>
                </div>
                {event.entityId && (
                  <div>
                    <dt>Entity</dt>
                    <dd>{event.entityId}</dd>
                  </div>
                )}
                {event.correlationId && (
                  <div>
                    <dt>Correlation</dt>
                    <dd>
                      {onCorrelationClick ? (
                        <button
                          type="button"
                          className="log-row__link log-row__link--action"
                          onClick={() => onCorrelationClick(event.correlationId)}
                        >
                          {event.correlationId}
                        </button>
                      ) : (
                        event.correlationId
                      )}
                    </dd>
                  </div>
                )}
              </dl>
            </div>
          </details>
        </li>
      ))}
    </ul>
  )
}
