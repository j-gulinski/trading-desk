import StatusPill from '../status/StatusPill.jsx'

export default function ServiceCard({ service }) {
  return (
    <div className={`service-card service-card--${service.level}`} role="listitem">
      <span className="service-card__name">{service.label}</span>
      <StatusPill level={service.level} compact />
      <div className="service-card__latency">
        <span className="service-card__latency-label">Latency</span>
        <span className="service-card__latency-value">
          {service.latencyMs != null ? (
            <>
              {service.latencyMs}
              <span className="unit">ms</span>
            </>
          ) : (
            '—'
          )}
        </span>
      </div>
    </div>
  )
}
