import { useEffect, useMemo, useState } from 'react'

function sanitizeVisibleColumns(stored, columns) {
  const columnById = new Map(columns.map((column) => [column.id, column]))
  const positionById = new Map(columns.map((column, index) => [column.id, index]))
  const ordered = []
  const seen = new Set()

  for (const columnId of stored) {
    if (!columnById.has(columnId) || seen.has(columnId)) continue
    ordered.push(columnId)
    seen.add(columnId)
  }

  for (const column of columns) {
    if (!column.required || seen.has(column.id)) continue
    const configuredPosition = positionById.get(column.id)
    const insertionIndex = ordered.findIndex(
      (candidate) => positionById.get(candidate) > configuredPosition,
    )
    ordered.splice(insertionIndex < 0 ? ordered.length : insertionIndex, 0, column.id)
  }

  return ordered
}

function readVisibleColumns(storageKey, columns, defaultColumns) {
  try {
    const stored = JSON.parse(window.localStorage.getItem(storageKey))
    if (!Array.isArray(stored)) return defaultColumns
    return sanitizeVisibleColumns(stored, columns)
  } catch {
    return defaultColumns
  }
}

function storeVisibleColumns(storageKey, visibleColumns) {
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(visibleColumns))
  } catch {
    return
  }
}

function moveColumn(visibleColumns, column, targetColumn, position) {
  const from = visibleColumns.indexOf(column)
  const to = visibleColumns.indexOf(targetColumn)
  if (from < 0 || to < 0 || from === to) return visibleColumns

  const next = [...visibleColumns]
  const [moved] = next.splice(from, 1)
  let insertionIndex = to + (position === 'after' ? 1 : 0)
  if (from < insertionIndex) insertionIndex -= 1
  next.splice(insertionIndex, 0, moved)
  return next
}

export function useTableState({
  columns,
  storageKey,
  defaultSort,
  fallbackSort = defaultSort,
  captureSnapshot,
  isSortable = (column) => Boolean(column?.sortable),
}) {
  const allColumnIds = useMemo(() => columns.map((column) => column.id), [columns])
  const columnById = useMemo(
    () => new Map(columns.map((column) => [column.id, column])),
    [columns],
  )

  const [visibleColumns, setVisibleColumns] = useState(() =>
    readVisibleColumns(storageKey, columns, allColumnIds),
  )
  const [sort, setSort] = useState(() => ({
    ...(visibleColumns.includes(defaultSort.column) ? defaultSort : fallbackSort),
    snapshot: null,
    capturedAt: null,
  }))

  useEffect(() => {
    storeVisibleColumns(storageKey, visibleColumns)
  }, [storageKey, visibleColumns])

  function applySort(column, direction) {
    const capturedAt = Date.now()
    setSort({
      column,
      direction,
      snapshot: columnById.get(column)?.snapshot
        ? captureSnapshot(column, capturedAt)
        : null,
      capturedAt,
    })
  }

  function applyDefaultSort(availableColumns = visibleColumns) {
    const next = availableColumns.includes(defaultSort.column) ? defaultSort : fallbackSort
    applySort(next.column, next.direction)
  }

  function toggleSort(column) {
    const config = columnById.get(column)
    if (!isSortable(config)) return
    const direction =
      sort.column === column
        ? sort.direction === 'asc'
          ? 'desc'
          : 'asc'
        : config.defaultDirection
    applySort(column, direction)
  }

  function toggleColumn(column) {
    const config = columnById.get(column)
    if (!config || config.required) return
    const hiding = visibleColumns.includes(column)
    const nextColumns = hiding
      ? visibleColumns.filter((candidate) => candidate !== column)
      : [...visibleColumns, column]
    setVisibleColumns(nextColumns)
    if (hiding && sort.column === column) applyDefaultSort(nextColumns)
  }

  function reorderColumn(column, targetColumn, position = 'before') {
    setVisibleColumns((current) => moveColumn(current, column, targetColumn, position))
  }

  function resetColumns() {
    setVisibleColumns(allColumnIds)
  }

  const resolvedColumns = useMemo(
    () => visibleColumns.map((column) => columnById.get(column)).filter(Boolean),
    [visibleColumns, columnById],
  )

  return {
    columns: resolvedColumns,
    visibleColumns,
    sort,
    applySort,
    applyDefaultSort,
    toggleSort,
    toggleColumn,
    reorderColumn,
    resetColumns,
  }
}
