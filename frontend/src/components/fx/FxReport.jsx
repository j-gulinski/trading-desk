import FilterChipGroup from '../filters/FilterChipGroup.jsx'
import {
  convertedTotalsOf,
  fxConversionOf,
  reportingCurrencyOptions,
} from '../../domain/fx.js'
import { formatAmount, formatSignedAmount } from '../../domain/formatting.js'

function metricValue(column, value) {
  if (!Number.isFinite(value)) return '—'
  return column.signed ? formatSignedAmount(value) : formatAmount(value)
}

function SubtotalRow({ row, columns, toCurrency, rates }) {
  const conversion = toCurrency
    ? fxConversionOf(rates?.[row.currency], row.currency, toCurrency)
    : null

  return (
    <li className="fx-report__row">
      <span className="fx-report__currency">{row.currency}</span>
      {columns.map((column) => (
        <span key={column.id} className="fx-report__value">
          <span className="fx-report__value-label">{column.label}</span>
          {metricValue(column, row.values[column.id])}
        </span>
      ))}
      {conversion != null && !conversion.identity && (
        <span className="fx-report__conversion">
          {conversion.rate != null ? (
            <span title={conversion.label}>{conversion.label}</span>
          ) : (
            <span className="fx-report__reason">{conversion.reason}</span>
          )}
        </span>
      )}
    </li>
  )
}

export default function FxReport({
  columns,
  subtotals,
  reportingCurrency,
  onReportingCurrencyChange,
  fx,
}) {
  if (subtotals.length === 0) return null
  const options = reportingCurrencyOptions(subtotals).map((currency) => ({
    value: currency,
    label: currency,
  }))
  const converted =
    reportingCurrency && fx.rates != null
      ? convertedTotalsOf(subtotals, fx.rates, reportingCurrency,
          columns.map((column) => column.id))
      : null

  return (
    <div className="fx-report">
      <div className="fx-report__head">
        <span className="fx-report__head-label">REPORTING CURRENCY</span>
        <FilterChipGroup
          options={options}
          value={reportingCurrency}
          onChange={onReportingCurrencyChange}
          ariaLabel="Reporting currency"
          className="fx-report__chips"
        />
        {!reportingCurrency && subtotals.length > 1 && (
          <span className="fx-report__hint">
            Choose a reporting currency for a combined total
          </span>
        )}
        {reportingCurrency && fx.error && (
          <span className="fx-report__hint fx-report__hint--warn">{fx.error}</span>
        )}
      </div>

      <ul className="fx-report__rows">
        {subtotals.map((row) => (
          <SubtotalRow
            key={row.currency}
            row={row}
            columns={columns}
            toCurrency={reportingCurrency}
            rates={fx.rates}
          />
        ))}
        {converted != null && (
          <li className="fx-report__row fx-report__row--total">
            <span className="fx-report__currency">→ {reportingCurrency}</span>
            {columns.map((column) => (
              <span key={column.id} className="fx-report__value">
                <span className="fx-report__value-label">{column.label}</span>
                {metricValue(column, converted.totals[column.id])}
              </span>
            ))}
            {converted.excluded.length > 0 && (
              <span className="fx-report__conversion" title={converted.applied.join('; ')}>
                {`excludes ${converted.excluded
                  .map((entry) => `${entry.currency} (${entry.reason})`)
                  .join(', ')}`}
              </span>
            )}
          </li>
        )}
      </ul>
    </div>
  )
}
