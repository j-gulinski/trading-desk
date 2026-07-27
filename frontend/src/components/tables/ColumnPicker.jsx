import { useEffect, useRef, useState } from 'react'

export default function ColumnPicker({
  ariaLabel = 'Table columns',
  columns,
  visibleColumns,
  onToggle,
  onReorder,
  onReset,
}) {
  const detailsRef = useRef(null)
  const summaryRef = useRef(null)
  const draggedColumnRef = useRef(null)
  const dragTargetRef = useRef(null)
  const dropPositionRef = useRef(null)
  const [draggedColumn, setDraggedColumn] = useState(null)
  const [dragTarget, setDragTarget] = useState(null)
  const [dropPosition, setDropPosition] = useState(null)
  const columnById = new Map(columns.map((column) => [column.id, column]))
  const visible = new Set(visibleColumns)
  const orderedColumns = [
    ...visibleColumns.map((column) => columnById.get(column)).filter(Boolean),
    ...columns.filter((column) => !visible.has(column.id)),
  ]

  useEffect(() => {
    function closeOnOutsidePointer(event) {
      const details = detailsRef.current
      if (details?.open && !details.contains(event.target)) details.open = false
    }

    function closeOnEscape(event) {
      const details = detailsRef.current
      if (event.key !== 'Escape' || !details?.open) return
      event.preventDefault()
      details.open = false
      summaryRef.current?.focus()
    }

    document.addEventListener('pointerdown', closeOnOutsidePointer)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('pointerdown', closeOnOutsidePointer)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [])

  function startDrag(event, column) {
    if (!visible.has(column) || (event.pointerType === 'mouse' && event.button !== 0)) {
      return
    }
    event.preventDefault()
    event.currentTarget.focus()
    event.currentTarget.setPointerCapture(event.pointerId)
    draggedColumnRef.current = column
    dragTargetRef.current = null
    dropPositionRef.current = null
    setDraggedColumn(column)
    setDragTarget(null)
    setDropPosition(null)
  }

  function moveDrag(event) {
    const dragging = draggedColumnRef.current
    if (!dragging) return
    const targetElement = document
      .elementFromPoint(event.clientX, event.clientY)
      ?.closest('[data-column-id]')
    const target = targetElement && detailsRef.current?.contains(targetElement)
      ? targetElement.dataset.columnId
      : null
    if (!target || target === dragging || !visible.has(target)) {
      if (dragTargetRef.current == null) return
      dragTargetRef.current = null
      dropPositionRef.current = null
      setDragTarget(null)
      setDropPosition(null)
      return
    }
    const rect = targetElement.getBoundingClientRect()
    const position = event.clientY < rect.top + rect.height / 2 ? 'before' : 'after'
    if (target === dragTargetRef.current && position === dropPositionRef.current) return
    dragTargetRef.current = target
    dropPositionRef.current = position
    setDragTarget(target)
    setDropPosition(position)
  }

  function stopDrag(event, commit) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
    if (commit && draggedColumnRef.current && dragTargetRef.current) {
      onReorder(
        draggedColumnRef.current,
        dragTargetRef.current,
        dropPositionRef.current,
      )
    }
    draggedColumnRef.current = null
    dragTargetRef.current = null
    dropPositionRef.current = null
    setDraggedColumn(null)
    setDragTarget(null)
    setDropPosition(null)
  }

  return (
    <details className="table-columns" ref={detailsRef}>
      <summary
        className="table-columns__summary"
        ref={summaryRef}
        aria-label={`${ariaLabel}, ${visibleColumns.length} of ${columns.length} shown`}
      >
        <span>Columns</span>
        <span className="table-columns__count">
          {visibleColumns.length}/{columns.length}
        </span>
      </summary>
      <div className="table-columns__menu">
        <div className="table-columns__heading">
          <span>Columns</span>
          <button type="button" className="table-columns__reset" onClick={onReset}>
            Reset
          </button>
        </div>
        <div
          className={`table-columns__options${draggedColumn ? ' table-columns__options--dragging' : ''}`}
          role="group"
          aria-label={ariaLabel}
        >
          {orderedColumns.map((column) => {
            const visibleIndex = visibleColumns.indexOf(column.id)
            const isVisible = visibleIndex >= 0
            return (
              <div
                className={`table-columns__option${draggedColumn === column.id ? ' table-columns__option--dragging' : ''}${dragTarget === column.id ? ` table-columns__option--target-${dropPosition}` : ''}`}
                key={column.id}
                data-column-id={column.id}
              >
                <label className="table-columns__toggle">
                  <input
                    type="checkbox"
                    checked={isVisible}
                    disabled={column.required}
                    onChange={() => onToggle(column.id)}
                  />
                  <span>{column.label}</span>
                </label>
                <button
                  type="button"
                  className={`table-columns__drag${draggedColumn === column.id ? ' table-columns__drag--active' : ''}`}
                  disabled={!isVisible}
                  aria-label={`Reorder ${column.label}. Drag, or use Arrow Up and Arrow Down`}
                  title={isVisible ? 'Drag to reorder' : 'Show column before reordering'}
                  onPointerDown={(event) => startDrag(event, column.id)}
                  onPointerMove={moveDrag}
                  onPointerUp={(event) => stopDrag(event, true)}
                  onPointerCancel={(event) => stopDrag(event, false)}
                  onKeyDown={(event) => {
                    const direction =
                      event.key === 'ArrowUp' ? -1 : event.key === 'ArrowDown' ? 1 : 0
                    if (
                      direction === 0 ||
                      visibleIndex + direction < 0 ||
                      visibleIndex + direction >= visibleColumns.length
                    ) {
                      return
                    }
                    event.preventDefault()
                    onReorder(
                      column.id,
                      visibleColumns[visibleIndex + direction],
                      direction < 0 ? 'before' : 'after',
                    )
                  }}
                >
                  <span aria-hidden="true">⠿</span>
                </button>
              </div>
            )
          })}
        </div>
        <span className="table-columns__note">
          Checked columns are shown. Drag a handle to reorder; focused handles also use
          Arrow Up and Arrow Down.
        </span>
      </div>
    </details>
  )
}
