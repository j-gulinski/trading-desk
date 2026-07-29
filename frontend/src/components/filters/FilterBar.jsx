import FilterChipGroup from './FilterChipGroup.jsx'

export default function FilterBar({ label, ariaLabel, options, value, onChange, search, children }) {
  return (
    <div className="filter-bar">
      <span className="filter-bar__label">{label}</span>
      <FilterChipGroup
        className="filter-bar__chips"
        ariaLabel={ariaLabel}
        options={options}
        value={value}
        onChange={onChange}
      />
      <div className="filter-bar__tools">
        {search && (
          <label className="filter-bar__search-field">
            <span className="filter-bar__label">{search.label}</span>
            <input
              className="filter-bar__search"
              type="search"
              placeholder={search.placeholder}
              value={search.value}
              onChange={(event) => search.onChange(event.target.value)}
            />
          </label>
        )}
        {children}
      </div>
    </div>
  )
}
