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
