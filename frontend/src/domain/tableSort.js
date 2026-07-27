export function compareValues(a, b) {
  if (a == null && b == null) return 0
  if (a == null) return 1
  if (b == null) return -1
  if (typeof a === 'string' && typeof b === 'string') return a.localeCompare(b)
  return a < b ? -1 : a > b ? 1 : 0
}

export function sortRows(rows, sort, { valueOf, tieBreak }) {
  const directionMultiplier = sort.direction === 'desc' ? -1 : 1

  return [...rows].sort((a, b) => {
    const aValue = valueOf(a, sort)
    const bValue = valueOf(b, sort)

    const aMissing = aValue == null
    const bMissing = bValue == null
    if (aMissing !== bMissing) return aMissing ? 1 : -1

    const comparison = compareValues(aValue, bValue)
    return comparison === 0 ? tieBreak(a, b) : comparison * directionMultiplier
  })
}
