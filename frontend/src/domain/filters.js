// Filter options whose display label differs from the value being filtered on
// (book id -> book name), sorted by label.
export function groupOptions(rows, valueOf, labelOf) {
  const options = new Map()
  for (const row of rows) {
    const value = valueOf(row)
    if (value == null) continue
    const option = options.get(value)
    if (option) option.count += 1
    else options.set(value, { value, label: labelOf(row), count: 1 })
  }
  return Array.from(options.values()).sort((a, b) => a.label.localeCompare(b.label))
}

export function countOptions(rows, valueOf) {
  const counts = new Map()
  for (const row of rows) {
    const value = valueOf(row)
    if (value == null) continue
    counts.set(value, (counts.get(value) ?? 0) + 1)
  }
  return Array.from(counts, ([value, count]) => ({ value, label: value, count })).sort(
    (a, b) => a.value.localeCompare(b.value),
  )
}
