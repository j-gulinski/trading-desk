import StatusPill from '../status/StatusPill.jsx'

export default function ServiceCard({ service }) {
  return (
    <div className={`service-card service-card--${service.level}`}>
      <div className="service-card__head">
        <span className="service-card__name">{service.label}</span>
        <StatusPill level={service.level} />
      </div>

      <div className="service-card__latency-label">LATENCY</div>
      <div className="service-card__latency">
        {service.latencyMs != null ? (
          <>
            {service.latencyMs}
            <span className="unit">ms</span>
          </>
        ) : (
          '—'
        )}
      </div>
    </div>
  )
}
