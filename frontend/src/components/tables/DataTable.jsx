function classes(...values) {
  return values.filter(Boolean).join(' ')
}

function ColumnLabel({ column }) {
  return (
    <>
      <span>{column.label}</span>
      {column.headerNote && (
        <span className="data-table__head-note">{column.headerNote}</span>
      )}
    </>
  )
}

function SortHeader({ column, sort, onSort, disabledReason }) {
  const active = sort.column === column.id
  const className = classes(column.numeric && 'data-table__cell--num', column.headerClass)

  if (!column.sortable) {
    return (
      <th scope="col" className={className || undefined}>
        <ColumnLabel column={column} />
      </th>
    )
  }

  return (
    <th
      scope="col"
      className={classes(className, 'data-table__sort-heading')}
      aria-sort={active ? (sort.direction === 'asc' ? 'ascending' : 'descending') : undefined}
    >
      <button
        type="button"
        className={classes(
          'data-table__sort',
          column.numeric && 'data-table__sort--num',
          active && 'data-table__sort--active',
        )}
        onClick={() => {
          if (!disabledReason) onSort(column.id)
        }}
        aria-disabled={disabledReason ? true : undefined}
        aria-label={disabledReason ? `${column.label}. ${disabledReason}` : undefined}
        title={disabledReason ?? undefined}
      >
        <span>
          <ColumnLabel column={column} />
        </span>
        <span className="data-table__sort-icon" aria-hidden="true">
          {active ? (sort.direction === 'asc' ? '▲' : '▼') : '↕'}
        </span>
      </button>
    </th>
  )
}

export default function DataTable({
  columns,
  rows,
  rowKey,
  renderCell,
  sort = { column: null, direction: 'desc' },
  onSort = () => {},
  sortDisabledReason = () => null,
  rowClassName = () => null,
  cellClassName = () => null,
  cellTitle = () => undefined,
  onRowClick = null,
  caption,
}) {
  const minWidth = Math.max(520, 500 + (columns.length - 2) * 80)

  return (
    <div className="data-table-wrap">
      <table className="data-table" style={{ minWidth }}>
        <caption className="data-table__caption">{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <SortHeader
                key={column.id}
                column={column}
                sort={sort}
                onSort={onSort}
                disabledReason={sortDisabledReason(column)}
              />
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const rowClass = classes(
              rowClassName(row),
              onRowClick && 'data-table__row--interactive',
            )
            return (
              <tr
                key={rowKey(row)}
                className={rowClass || undefined}
                tabIndex={onRowClick ? 0 : undefined}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                onKeyDown={
                  onRowClick
                    ? (event) => {
                        if (event.key !== 'Enter' && event.key !== ' ') return
                        event.preventDefault()
                        onRowClick(row)
                      }
                    : undefined
                }
              >
                {columns.map((column) => (
                  <td
                    key={column.id}
                    className={
                      classes(
                        column.numeric && 'data-table__cell--num',
                        column.cellClass,
                        cellClassName(column, row),
                      ) || undefined
                    }
                    title={cellTitle(column, row)}
                  >
                    {renderCell(column, row)}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
