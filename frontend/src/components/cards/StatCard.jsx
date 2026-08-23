export default function StatCard({ label, value, sub, tone = 'default', href, title }) {
  const Root = href ? 'a' : 'div'
  const classes = [
    'stat-card',
    `stat-card--${tone}`,
    href ? 'stat-card--link' : null,
  ].filter(Boolean).join(' ')

  return (
    <Root className={classes} href={href} title={title}>
      <div className="stat-card__label">{label}</div>
      <div className="stat-card__value">{value}</div>
      {sub != null && <div className="stat-card__sub">{sub}</div>}
    </Root>
  )
}
