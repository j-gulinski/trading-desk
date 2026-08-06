import { useState } from 'react'
import { usePolling } from '../../hooks/usePolling.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import {
  useMarketFeedContext,
  useValuationFeedContext,
} from '../../providers/feedContext.js'
import { apiGet } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import { normalizeServiceStatus, summarize } from '../../domain/serviceStatus.js'
import { normalizeAuditEvents } from '../../domain/auditEvents.js'
import { formatClockTime, formatElapsedTime, formatNumber } from '../../domain/formatting.js'
import { summarizeFeed } from '../../domain/marketData.js'
import { summarizeValuations, valuationRowsOf } from '../../domain/valuations.js'
import ServiceCard from '../../components/cards/ServiceCard.jsx'
import StatCard from '../../components/cards/StatCard.jsx'
import Panel from '../../components/Panel.jsx'
import EmptyState from '../../components/EmptyState.jsx'
import FilterChipGroup from '../../components/filters/FilterChipGroup.jsx'
import AuditEventList from '../../components/audit/AuditEventList.jsx'
import StatusPill from '../../components/status/StatusPill.jsx'
import { ERROR_WINDOW_MS } from '../../config/monitoring.js'
import { streamStatusLevel } from '../../config/stream.js'

const FILTER_LEVELS = ['healthy', 'degraded', 'stale', 'down', 'unknown']
const ERROR_SEVERITIES = ['WARNING', 'ERROR', 'CRITICAL']


export default function SystemOverview() {
  const [activeLevel, setActiveLevel] = useState(null)
  const marketFeed = useMarketFeedContext()
  const valuationFeed = useValuationFeedContext()
  const { data, error, loading, lastPolled, lastUpdated } = usePolling(
    ({ signal }) => apiGet(endpoints.monitoring.status, { signal }),
  )

  const { now, elapsedMs: pollAgeMs } = useElapsedTime(lastPolled)

  const audits = usePolling(({ signal }) =>
    apiGet(
      endpoints.monitoring.audits({
        severity: ERROR_SEVERITIES,
        since: new Date(Date.now() - ERROR_WINDOW_MS).toISOString(),
        limit: 100,
      }),
      { signal },
    ),
  )
  const auditEvents = normalizeAuditEvents(audits.data)

  const services = normalizeServiceStatus(data, {
    now,
    monitoringCheckedAtMs: lastUpdated,
    monitoringUnavailable: error != null,
  })
  const summary = summarize(services)
  const marketSummary = summarizeFeed(Object.values(marketFeed.instruments), now)
  const valuationSummary = summarizeValuations(
    valuationRowsOf(Object.values(valuationFeed.valuations), now),
  )
  const streamsLastUpdateMs = Math.max(
    marketSummary.lastUpdateMs ?? 0,
    valuationSummary.lastUpdateMs ?? 0,
  ) || null
  const visibleServices = activeLevel
    ? services.filter((service) => service.level === activeLevel)
    : services
  const filterOptions = FILTER_LEVELS
    .filter((level) => level !== 'unknown' || summary.unknown > 0 || activeLevel === 'unknown')
    .map((level) => ({ value: level, label: level, count: summary[level], tone: level }))

  return (
    <section className="page">
      <div className="overview__section-head">
        <div className="overview__section-copy">
          <h2 className="overview__section-title">Service health</h2>
          <span className="overview__section-meta">
            {summary.total} services
            {pollAgeMs != null && ` · polled ${formatElapsedTime(pollAgeMs)}`}
            {error && ' · retrying'}
          </span>
        </div>
        <FilterChipGroup
          className="overview__summary"
          ariaLabel="Filter services by health"
          options={filterOptions}
          value={activeLevel}
          onChange={setActiveLevel}
        />
      </div>

      {loading && <EmptyState message="Loading service health…" />}

      {!loading && (
        <>
          {visibleServices.length > 0 ? (
            <div className="service-grid" role="list">
              {visibleServices.map((service) => (
                <ServiceCard key={service.id} service={service} />
              ))}
            </div>
          ) : (
            <EmptyState message={`No ${activeLevel} services.`} />
          )}
        </>
      )}

      <div className="overview__panels">
        <Panel
          className="overview__streams"
          title="Live streams"
          meta={
            <>
              <StatusPill
                level={streamStatusLevel(marketFeed.status)}
                label={`MARKET ${marketFeed.status}`}
              />
              <StatusPill
                level={streamStatusLevel(valuationFeed.status)}
                label={`PRICING ${valuationFeed.status}`}
              />
            </>
          }
        >
          <div className="overview__stream-summary">
            <StatCard
              label="TICKS RECEIVED"
              value={formatNumber(marketFeed.tickCount)}
              sub="this tab session"
            />
            <StatCard
              label="INSTRUMENTS"
              value={marketSummary.total}
              sub={`${marketSummary.live} live · ${marketSummary.stale} stale`}
            />
            <StatCard
              label="VALUATIONS"
              value={valuationSummary.total}
              sub={`${valuationSummary.open} open · ${valuationSummary.closed} closed`}
            />
            <StatCard
              label="FRESHNESS"
              value={`${valuationSummary.live} / ${valuationSummary.live + valuationSummary.stale}`}
              sub="live of open valuations"
              tone={valuationSummary.stale > 0 ? 'warn' : 'default'}
            />
            <StatCard
              label="LAST UPDATE"
              value={formatClockTime(streamsLastUpdateMs)}
              sub="newest event, either stream"
            />
          </div>
        </Panel>
      </div>

      <div className="overview__panels">
        <Panel
          title="Errors & warnings · last 5 min"
          meta={audits.error ? 'UNAVAILABLE' : auditEvents.length || null}
        >
          {audits.loading && <EmptyState message="Loading recent events…" />}
          {!audits.loading && audits.error && (
            <EmptyState message="Audit feed unavailable — retrying." />
          )}
          {!audits.loading && !audits.error && auditEvents.length === 0 && (
            <EmptyState message="No warnings or errors in the last 5 minutes." />
          )}
          {!audits.loading && !audits.error && auditEvents.length > 0 && (
            <AuditEventList events={auditEvents} />
          )}
        </Panel>
      </div>

      <div className="overview__panels">
        <Panel title="Logs · all services">
          <EmptyState message="Central log stream not published by the backend yet." />
        </Panel>
      </div>
    </section>
  )
}
