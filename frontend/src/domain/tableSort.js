function compareValues(a, b) {
  if (Array.isArray(a) && Array.isArray(b)) {
    for (let index = 0; index < Math.min(a.length, b.length); index += 1) {
      const comparison = compareValues(a[index], b[index])
      if (comparison !== 0) return comparison
    }
    return a.length - b.length
  }
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
