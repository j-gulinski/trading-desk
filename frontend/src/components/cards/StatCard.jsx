export default function StatCard({ label, value, sub, tone = 'default' }) {
  return (
    <div className={`stat-card stat-card--${tone}`}>
      <div className="stat-card__label">{label}</div>
      <div className="stat-card__value">{value}</div>
      {sub != null && <div className="stat-card__sub">{sub}</div>}
    </div>
  )
}
