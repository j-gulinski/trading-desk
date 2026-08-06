import { useMarketFeedContext, useValuationFeedContext } from '../providers/feedContext.js'
import { STREAM_STATUS, streamStatusLevel } from '../config/stream.js'

const LABEL = {
  [STREAM_STATUS.connected]: 'connected',
  [STREAM_STATUS.connecting]: 'connecting',
  [STREAM_STATUS.reconnecting]: 'reconnecting',
}

function weakest(statuses) {
  const order = [
    STREAM_STATUS.reconnecting,
    STREAM_STATUS.connecting,
    STREAM_STATUS.connected,
  ]
  return order.find((status) => statuses.includes(status)) ?? STREAM_STATUS.connecting
}

export default function StreamsBadge() {
  const market = useMarketFeedContext()
  const valuations = useValuationFeedContext()

  const statuses = [market.status, valuations.status]
  const connected = statuses.filter((status) => status === STREAM_STATUS.connected).length
  const overall = weakest(statuses)
  const summary = `${connected} / ${statuses.length} streams · ${LABEL[overall] ?? 'unknown'}`

  return (
    <div
      className={`streams-badge streams-badge--${streamStatusLevel(overall)}`}
      role="status"
      aria-label={summary}
      title={summary}
    >
      <span className="streams-badge__dot" aria-hidden="true" />
      <span className="streams-badge__text streams-badge__text--full" aria-hidden="true">
        {summary}
      </span>
      <span className="streams-badge__text streams-badge__text--compact" aria-hidden="true">
        {connected}/{statuses.length}
      </span>
    </div>
  )
}
