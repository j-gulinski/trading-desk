import { ALPHA_BETA_UNAVAILABLE } from '../../config/valuations.js'
import { directionOf, formatSignedAmount } from '../../domain/formatting.js'

function Metric({ label, value, className }) {
  return (
    <div className="book-card__metric">
      <span className="book-card__label">{label}</span>
      <span className={`book-card__value ${className}`}>{value}</span>
    </div>
  )
}

export default function BookRiskCard({ book }) {
  const tone = directionOf(book.unrealized)

  return (
    <article className={`book-card stat-card stat-card--${tone}`}>
      <header className="book-card__head">
        <span className="book-card__name">{book.name}</span>
        <span className="book-card__class">{book.assetClass}</span>
      </header>

      <div className="book-card__metrics">
        <Metric label="ALPHA" value="n/a" className="book-card__value--missing" />
        <Metric label="BETA" value="n/a" className="book-card__value--missing" />
        <Metric
          label="UNREAL."
          value={formatSignedAmount(book.unrealized)}
          className={`book-card__value--total delta--${tone}`}
        />
      </div>

      <footer className="book-card__note">
        {ALPHA_BETA_UNAVAILABLE} · {book.open} open · {book.live} live
      </footer>
    </article>
  )
}
