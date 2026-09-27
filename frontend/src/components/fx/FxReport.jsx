import FilterChipGroup from '../filters/FilterChipGroup.jsx'
import { reportingCurrencyOptions } from '../../domain/fx.js'
import { formatAmount, formatSignedAmount } from '../../domain/formatting.js'

const COLUMNS = [
  { id: 'grossEntry', label: 'GROSS ENTRY', signed: false },
  { id: 'unrealized', label: 'UNREALIZED PNL', signed: true },
  { id: 'realized', label: 'REALIZED PNL', signed: true },
  { id: 'total', label: 'TOTAL PNL', signed: true },
]

const OPEN_COLUMNS = COLUMNS.slice(0, 2)

function metricValue(column, value) {
  return column.signed ? formatSignedAmount(value) : formatAmount(value)
}

function SubtotalRow({ row, columns }) {
  const { fx } = row

  return (
    <li className="fx-report__row">
      <span className="fx-report__currency">{row.currency}</span>
      {columns.map((column) => (
        <span key={column.id} className="fx-report__value">
          <span className="fx-report__value-label">{column.label}</span>
          {metricValue(column, row.values[column.id])}
        </span>
      ))}
      {(fx?.label || fx?.reason) && (
        <span className="fx-report__conversion">
          {fx.label ? (
            <span title={fx.label}>{fx.label}</span>
          ) : (
            <span className="fx-report__reason">{fx.reason}</span>
          )}
        </span>
      )}
    </li>
  )
}

export default function FxReport({
  currency,
  portfolio,
  reportingCurrency,
  onReportingCurrencyChange,
}) {
  const { subtotals, reported } = portfolio
  if (subtotals.length === 0) return null
  const columns = portfolio.closedTrades > 0 ? COLUMNS : OPEN_COLUMNS
  const currencies = reportingCurrencyOptions(subtotals)
  if (reportingCurrency && !currencies.includes(reportingCurrency)) {
    currencies.push(reportingCurrency)
    currencies.sort()
  }
  const options = currencies.map((code) => ({ value: code, label: code }))

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
      </div>

      <ul className="fx-report__rows">
        {subtotals.map((row) => (
          <SubtotalRow key={row.currency} row={row} columns={columns} />
        ))}
        {currency != null && (
          <li className="fx-report__row fx-report__row--total">
            <span className="fx-report__currency">→ {currency}</span>
            {columns.map((column) => (
              <span key={column.id} className="fx-report__value">
                <span className="fx-report__value-label">{column.label}</span>
                {metricValue(column, reported.values[column.id])}
              </span>
            ))}
            {reported.title && (
              <span className="fx-report__conversion">
                <span className="fx-report__reason">No total — {reported.title}</span>
              </span>
            )}
          </li>
        )}
      </ul>
    </div>
  )
}
