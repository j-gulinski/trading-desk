import { Fragment } from 'react'
import { payloadEntriesOf } from '../../domain/logLines.js'

function displayValue(key, value) {
  if (key === 'response_json' && typeof value === 'string') {
    try {
      return JSON.stringify(JSON.parse(value), null, 2)
    } catch {
      return value
    }
  }
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

export default function LogPayload({ payload, onTradeClick, onCorrelationClick, activeId }) {
  const entries = payloadEntriesOf(payload)
  if (entries.length === 0) return null

  const handlerFor = (key, value) => {
    if (typeof value !== 'string' || value === activeId) return null
    if (key === 'trade_id') return onTradeClick
    if (key === 'correlation_id') return onCorrelationClick
    return null
  }

  return (
    <dl className="log-payload">
      {entries.map(([key, value]) => {
        const onClick = handlerFor(key, value)
        return (
          <Fragment key={key}>
            <dt className="log-payload__key">{key}</dt>
            <dd className="log-payload__value">
              {onClick ? (
                <button
                  type="button"
                  className="log-payload__action"
                  onClick={() => onClick(value)}
                >
                  {value}
                </button>
              ) : (
                displayValue(key, value)
              )}
            </dd>
          </Fragment>
        )
      })}
    </dl>
  )
}
