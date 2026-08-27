import { directionOf, formatPercent, formatSignedAmount } from '../../domain/formatting.js'
import { assetClassLabel } from '../../config/tradeActions.js'

function Metric({ label, value, className, title }) {
  return (
    <div className="book-card__metric" title={title}>
      <span className="book-card__label">{label}</span>
      <span className={`book-card__value ${className}`}>{value}</span>
    </div>
  )
}

function formatCapital(value) {
  if (!Number.isFinite(value)) return null
  return value >= 1e6
    ? `USD ${(value / 1e6).toFixed(value % 1e6 ? 1 : 0)}m`
    : `USD ${value}`
}

export default function BookRiskCard({ book }) {
  const tone = directionOf(book.unrealizedReported)
  const ready = book.riskStatus === 'READY'
  const windowed = ready && Number.isFinite(book.alphaWindowReturn)
  const bookReturn = Number.isFinite(book.bookWindowReturn)
    ? formatPercent(book.bookWindowReturn * 100, 2)
    : 'n/a'
  const bookReturnTitle = Number.isFinite(book.bookWindowPnl)
    ? `${formatSignedAmount(book.bookWindowPnl)} PnL over the last ${book.riskObservations} samples` +
      (Number.isFinite(book.benchmarkWindowReturn)
        ? ` · ${book.benchmark} did ${formatPercent(book.benchmarkWindowReturn * 100, 2)} — this comparison drives alpha and beta`
        : '')
    : undefined
  const alpha = windowed
    ? formatPercent(book.alphaWindowReturn * 100, 2)
    : ready && Number.isFinite(book.alpha)
      ? formatPercent(book.alpha * 100, 4)
      : 'n/a'
  const alphaTitle = windowed
    ? `Over the same window: ${formatSignedAmount(book.alphaWindowPnl)} PnL not explained by the market move`
    : undefined
  const beta = ready && Number.isFinite(book.beta) ? book.beta.toFixed(4) : 'n/a'
  const capital = formatCapital(book.capitalBase)
  const betaTitle =
    ready && Number.isFinite(book.dollarBeta)
      ? `≈ ${formatSignedAmount(book.dollarBeta / 100)} PnL per +1% ${book.benchmark}` +
        (capital ? ` · assumes ${capital} capital base` : '')
      : undefined
  const rSquared = ready && Number.isFinite(book.rSquared) ? ` · R² ${book.rSquared.toFixed(2)}` : ''
  const lowFit = ready && Number.isFinite(book.rSquared) && book.rSquared < 0.05
  const riskNote = ready
    ? `${book.riskObservations}/${book.riskWindow} returns${rSquared}${lowFit ? ' · low fit' : ''}`
    : book.riskStatus === 'ZERO_BENCHMARK_VARIANCE'
      ? 'benchmark variance zero'
      : `${book.riskObservations ?? 0}/${book.riskMinimumObservations ?? 20} returns`
  const breakdown =
    windowed &&
    Number.isFinite(book.beta) &&
    Number.isFinite(book.benchmarkWindowReturn) &&
    Number.isFinite(book.bookWindowReturn)
      ? {
          marketReturn: book.beta * book.benchmarkWindowReturn,
          marketPnl: Number.isFinite(book.dollarBeta)
            ? book.dollarBeta * book.benchmarkWindowReturn
            : null,
        }
      : null

  return (
    <article className={`book-card stat-card stat-card--${tone}`}>
      <header className="book-card__head">
        <span className="book-card__name" title={book.name}>{book.name}</span>
        <span className="book-card__class">{assetClassLabel(book.assetClass)}</span>
      </header>

      <div className="book-card__metrics">
        <Metric
          label="RETURN"
          value={bookReturn}
          title={bookReturnTitle}
          className={Number.isFinite(book.bookWindowReturn) ? '' : 'book-card__value--missing'}
        />
        <Metric
          label="ALPHA"
          value={alpha}
          title={alphaTitle}
          className={ready ? '' : 'book-card__value--missing'}
        />
        <Metric
          label="BETA"
          value={beta}
          title={betaTitle}
          className={ready ? '' : 'book-card__value--missing'}
        />
        <Metric
          label={`UNREAL. · ${book.unrealizedCurrency}`}
          value={
            book.unrealizedReported == null
              ? '—'
              : formatSignedAmount(book.unrealizedReported)
          }
          title={book.unrealizedNote}
          className={`book-card__value--total delta--${tone}`}
        />
      </div>

      {breakdown && (
        <details className="book-card__breakdown">
          <summary>return details</summary>
          <div className="book-card__breakdown-rows">
            <span className="book-card__breakdown-label" title={`The share of this window's result the ${book.benchmark} move accounts for, given the book's beta`}>
              β {book.beta.toFixed(2)} × index {formatPercent(book.benchmarkWindowReturn * 100, 2)}
            </span>
            <span className="book-card__breakdown-pct">
              {formatPercent(breakdown.marketReturn * 100, 2)}
            </span>
            <span className="book-card__breakdown-usd">
              {breakdown.marketPnl != null ? formatSignedAmount(breakdown.marketPnl) : ''}
            </span>

            <span className="book-card__breakdown-label" title="PnL the index move cannot explain — the regression intercept summed over the window">
              + α beyond the market
            </span>
            <span className="book-card__breakdown-pct">
              {formatPercent(book.alphaWindowReturn * 100, 2)}
            </span>
            <span className="book-card__breakdown-usd">
              {Number.isFinite(book.alphaWindowPnl) ? formatSignedAmount(book.alphaWindowPnl) : ''}
            </span>

            <span className="book-card__breakdown-label book-card__breakdown-total">
              ≈ return this window
            </span>
            <span className="book-card__breakdown-pct book-card__breakdown-total">{bookReturn}</span>
            <span className="book-card__breakdown-usd book-card__breakdown-total">
              {Number.isFinite(book.bookWindowPnl) ? formatSignedAmount(book.bookWindowPnl) : ''}
            </span>
          </div>
          {Number.isFinite(book.dollarBeta) && (
            <p className="book-card__breakdown-meta">
              each +1% index move ≈ {formatSignedAmount(book.dollarBeta / 100)} PnL
              {capital ? ` · assumes ${capital} capital` : ''}
            </p>
          )}
        </details>
      )}

      <footer className="book-card__note">
        {riskNote} · {book.open} open · {book.live} live
      </footer>
    </article>
  )
}
