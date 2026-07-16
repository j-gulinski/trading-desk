export default function FilterChipGroup({
  options,
  value,
  onChange,
  ariaLabel = 'Filters',
  className = '',
}) {
  const classes = ['filter-chip-group', className].filter(Boolean).join(' ')

  return (
    <div className={classes} role="group" aria-label={ariaLabel}>
      {options.map((option) => {
        const selected = value === option.value
        const tone = option.tone ?? option.value

        return (
          <button
            key={option.value}
            type="button"
            className="filter-chip"
            aria-pressed={selected}
            onClick={() => onChange(selected ? null : option.value)}
          >
            {tone && (
              <span className={`filter-chip__dot filter-chip__dot--${tone}`} />
            )}
            {option.count != null && <span>{option.count}</span>}
            {option.label}
          </button>
        )
      })}
    </div>
  )
}
