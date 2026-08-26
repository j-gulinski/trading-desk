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
      <th scope="col" className={className || undefined} data-column={column.id}>
        <ColumnLabel column={column} />
      </th>
    )
  }

  return (
    <th
      scope="col"
      className={classes(className, 'data-table__sort-heading')}
      data-column={column.id}
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
  cellProps = () => null,
  onRowClick = null,
  onRowMouseEnter = null,
  onRowMouseLeave = null,
  caption,
  tableClassName,
  wrapClassName,
  minWidth: requestedMinWidth,
}) {
  const minWidth = requestedMinWidth ?? Math.max(520, 500 + (columns.length - 2) * 80)

  return (
    <div className={classes('data-table-wrap', wrapClassName)}>
      <table className={classes('data-table', tableClassName)} style={{ minWidth }}>
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
          {rows.map((row, rowIndex) => {
            const rowClass = classes(
              rowClassName(row),
              onRowClick && 'data-table__row--interactive',
            )
            return (
              <tr
                key={rowKey(row)}
                className={rowClass || undefined}
                data-panel-trigger={onRowClick ? '' : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                onMouseEnter={onRowMouseEnter ? () => onRowMouseEnter(row) : undefined}
                onMouseLeave={onRowMouseLeave ? () => onRowMouseLeave(row) : undefined}
                onKeyDown={onRowClick ? (event) => {
                  if (event.target !== event.currentTarget) return
                  if (event.key !== 'Enter' && event.key !== ' ') return
                  event.preventDefault()
                  onRowClick(row)
                } : undefined}
              >
                {columns.map((column) => {
                  const props = cellProps(column, row, rowIndex) ?? {}
                  if (props.skip) return null
                  return (
                    <td
                      key={column.id}
                      data-column={column.id}
                      rowSpan={props.rowSpan}
                      className={
                        classes(
                          column.numeric && 'data-table__cell--num',
                          column.cellClass,
                          props.className,
                          cellClassName(column, row),
                        ) || undefined
                      }
                      title={cellTitle(column, row)}
                    >
                      {renderCell(column, row)}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
