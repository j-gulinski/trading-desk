import LoadingSkeleton from '../LoadingSkeleton.jsx'
import StatusPill from '../status/StatusPill.jsx'

export default function TicketValue({
  label,
  hint,
  value,
  unit,
  tone,
  loading,
  placeholder,
  pill,
  total,
  totalNote,
  assumptions,
  error,
}) {
  return (
    <section className="ticket-value" aria-live="polite">
      <div className="ticket-value__head">
        <span
          className={`ticket-value__label${hint ? ' ticket-value__label--hinted' : ''}`}
          title={hint}
        >
          {label}
        </span>
        {pill && <StatusPill level={pill.level} label={pill.label} title={pill.title} compact />}
      </div>
      <div className="ticket-value__main">
        {loading ? (
          <LoadingSkeleton variant="inline" label="Computing model value" />
        ) : value != null ? (
          <>
            <strong className={tone ? `delta--${tone}` : undefined}>{value}</strong>
            {unit && <span className="ticket-value__unit">{unit}</span>}
          </>
        ) : (
          <span className="ticket-value__placeholder">{placeholder}</span>
        )}
      </div>
      {total != null && (
        <div className="ticket-value__total">
          <strong>{total}</strong>
          {totalNote && <span>{totalNote}</span>}
        </div>
      )}
      {assumptions.length > 0 && (
        <dl className="ticket-value__assumptions">
          {assumptions.map((item) => (
            <div key={item.label}>
              <dt>{item.label}</dt>
              <dd>{item.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {error && <p className="panel-form__error" role="alert">{error}</p>}
    </section>
  )
}
