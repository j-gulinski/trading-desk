import { useState } from 'react'
import { usePolling } from '../../hooks/usePolling.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import { apiGet } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import { normalizeServiceStatus, summarize } from '../../domain/serviceStatus.js'
import { formatElapsedTime } from '../../domain/formatting.js'
import ServiceCard from '../../components/cards/ServiceCard.jsx'
import Panel from '../../components/Panel.jsx'
import EmptyState from '../../components/EmptyState.jsx'
import FilterChipGroup from '../../components/filters/FilterChipGroup.jsx'

const FILTER_LEVELS = ['healthy', 'degraded', 'stale', 'down', 'unknown']

export default function SystemOverview() {
  const [activeLevel, setActiveLevel] = useState(null)
  const { data, error, loading, lastPolled, lastUpdated } = usePolling(
    ({ signal }) => apiGet(endpoints.monitoring.status, { signal }),
  )

  const { now, elapsedMs: pollAgeMs } = useElapsedTime(lastPolled)
  const services = normalizeServiceStatus(data, {
    now,
    monitoringCheckedAtMs: lastUpdated,
    monitoringUnavailable: error != null,
  })
  const summary = summarize(services)
  const visibleServices = activeLevel
    ? services.filter((service) => service.level === activeLevel)
    : services
  const filterOptions = FILTER_LEVELS
    .filter((level) => level !== 'unknown' || summary.unknown > 0 || activeLevel === 'unknown')
    .map((level) => ({ value: level, label: level, count: summary[level], tone: level }))

  return (
    <section className="page">
      <div className="overview__section-head">
        <span className="overview__section-title">
          SERVICE HEALTH · {summary.total} SERVICES
          {pollAgeMs != null && ` · POLLED ${formatElapsedTime(pollAgeMs)}`}
          {error && ' · RETRYING'}
        </span>
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
            <div className="service-grid">
              {visibleServices.map((service) => (
                <ServiceCard key={service.id} service={service} />
              ))}
            </div>
          ) : (
            <EmptyState message={`No ${activeLevel} services.`} />
          )}
        </>
      )}

      <div className="overview__panels overview__panels--two">
        <Panel title="SSE CONNECTIONS">
          <EmptyState message="Live stream status arrives with Market Data." />
        </Panel>
        <Panel title="ERRORS · LAST 5 MIN">
          <EmptyState message="No error feed published by the backend yet." />
        </Panel>
      </div>

      <div className="overview__panels">
        <Panel title="LOGS · ALL SERVICES">
          <EmptyState message="Central log stream not published by the backend yet." />
        </Panel>
      </div>
    </section>
  )
}
