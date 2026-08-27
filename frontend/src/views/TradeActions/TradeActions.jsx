import { usePolling } from '../../hooks/usePolling.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import { apiGet } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import { normalizeAuditEvents } from '../../domain/auditEvents.js'
import { intentRowsOf, lastActionAtOf, queueStatusOf, summarizeIntents } from '../../domain/tradeActions.js'
import { formatClockTime, formatElapsedTime, formatNumber } from '../../domain/formatting.js'
import Panel from '../../components/Panel.jsx'
import EmptyState from '../../components/EmptyState.jsx'
import LoadingSkeleton from '../../components/LoadingSkeleton.jsx'
import StatCard from '../../components/cards/StatCard.jsx'
import StatusPill from '../../components/status/StatusPill.jsx'
import IntentFeed from '../../components/tradeactions/IntentFeed.jsx'
import {
  FEED_EVENT_TYPES,
  FEED_LIMIT,
  FEED_POLL_INTERVAL_MS,
  FEED_SERVICE,
  QUEUE_POLL_INTERVAL_MS,
} from '../../config/tradeActions.js'

export default function TradeActions() {
  const queue = usePolling(
    ({ signal }) => apiGet(endpoints.tradeAction.queueStatus, { signal }),
    { intervalMs: QUEUE_POLL_INTERVAL_MS },
  )

  const feed = usePolling(
    ({ signal }) => apiGet(
      endpoints.monitoring.audits({
        service: FEED_SERVICE,
        event_type: FEED_EVENT_TYPES,
        limit: FEED_LIMIT,
      }),
      { signal },
    ),
    { intervalMs: FEED_POLL_INTERVAL_MS },
  )

  const { elapsedMs: pollAgeMs } = useElapsedTime(queue.lastPolled)

  const status = queueStatusOf(queue.error ? null : queue.data)
  const rows = intentRowsOf(normalizeAuditEvents(feed.data))
  const rejected = summarizeIntents(rows).rejected
  const lastActionMs = lastActionAtOf(rows)
  const unreachable = queue.error != null
  const windowed = rows.length >= FEED_LIMIT

  return (
    <section className="page">
      <div className="trade-actions__stats">
        <StatCard
          label="CURRENT PROCESS · ACCEPTED"
          value={unreachable ? '—' : formatNumber(status.accepted)}
          sub={`${formatNumber(status.processed)} processed since restart`}
        />
        <StatCard
          label="CURRENT PROCESS · WRITTEN"
          value={unreachable ? '—' : formatNumber(status.created + status.closed)}
          sub={`${formatNumber(status.created)} opened · ${formatNumber(status.closed)} closed since restart`}
        />
        <StatCard
          label="RECENT FEED · REJECTED"
          value={feed.error ? '—' : formatNumber(rejected)}
          sub={`of ${rows.length} recent actions · ${formatNumber(status.rejected)} since restart`}
          tone={rejected > 0 ? 'warn' : 'default'}
        />
        <StatCard
          label="CURRENT PROCESS · AVG TIME"
          value={
            !unreachable && status.avgProcessingMs != null
              ? `${formatNumber(status.avgProcessingMs)} ms`
              : 'n/a'
          }
          sub={
            status.lastProcessingMs != null
              ? `last ${formatNumber(status.lastProcessingMs)} ms · dequeue → commit`
              : 'dequeue → commit'
          }
        />
        <StatCard
          label="LAST AUDITED ACTION"
          value={lastActionMs != null ? formatClockTime(lastActionMs, { millis: true, day: true }) : '—'}
          sub="local time · recent feed"
        />
      </div>

      <Panel
        title="RECENT ACTIONS · ACCEPTED / REJECTED"
        meta={
          <>
            {feed.error
              ? <StatusPill level="down" label="UNAVAILABLE" />
              : <StatusPill level="healthy" label="CONNECTED" />}
            <span>
              {windowed ? `newest ${FEED_LIMIT} events` : `${rows.length} recent events`}
              {pollAgeMs != null && ` · checked ${formatElapsedTime(pollAgeMs)}`}
            </span>
          </>
        }
      >
        {feed.loading && <LoadingSkeleton variant="list" label="Loading recent actions" />}
        {!feed.loading && feed.error && (
          <EmptyState message="Audit feed unavailable — retrying." />
        )}
        {!feed.loading && !feed.error && rows.length === 0 && (
          <EmptyState message="No trade actions recorded yet." />
        )}
        {!feed.loading && !feed.error && rows.length > 0 && (
          <IntentFeed rows={rows} />
        )}
      </Panel>
    </section>
  )
}
