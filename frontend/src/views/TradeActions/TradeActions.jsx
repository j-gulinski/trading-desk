import { usePolling } from '../../hooks/usePolling.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import { apiGet } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import { normalizeAuditEvents } from '../../domain/auditEvents.js'
import { intentRowsOf, lastActionAtOf, summarizeIntents } from '../../domain/tradeActions.js'
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
} from '../../config/tradeActions.js'

export default function TradeActions() {
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

  const { elapsedMs: pollAgeMs } = useElapsedTime(feed.lastPolled)

  const rows = intentRowsOf(normalizeAuditEvents(feed.data))
  const summary = summarizeIntents(rows)
  const lastActionMs = lastActionAtOf(rows)
  const unavailable = feed.error != null
  const windowed = rows.length >= FEED_LIMIT

  return (
    <section className="page">
      <div className="trade-actions__stats">
        <StatCard
          label="RECENT FEED · OPENED"
          value={unavailable ? '—' : formatNumber(summary.opened)}
          sub={`of ${rows.length} recent actions`}
        />
        <StatCard
          label="RECENT FEED · CLOSED"
          value={unavailable ? '—' : formatNumber(summary.closed)}
          sub={`${formatNumber(summary.moved)} moved between books`}
        />
        <StatCard
          label="RECENT FEED · REJECTED"
          value={unavailable ? '—' : formatNumber(summary.rejected)}
          sub={`of ${rows.length} recent actions`}
          tone={summary.rejected > 0 ? 'warn' : 'default'}
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
            {unavailable
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
