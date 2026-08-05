export default function PanelTabs({ tabs, activeId, onSelect, idPrefix }) {
  function handleKeyDown(event) {
    const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
    if (step === 0) return
    event.preventDefault()
    const index = tabs.findIndex((tab) => tab.id === activeId)
    const next = tabs[(index + step + tabs.length) % tabs.length]
    onSelect(next.id)
    document.getElementById(`${idPrefix}-tab-${next.id}`)?.focus()
  }

  return (
    <div className="panel-tabs" role="tablist" aria-label="Detail sections">
      {tabs.map((tab) => {
        const selected = tab.id === activeId
        return (
          <button
            key={tab.id}
            id={`${idPrefix}-tab-${tab.id}`}
            type="button"
            role="tab"
            className="panel-tabs__tab"
            aria-selected={selected}
            aria-controls={`${idPrefix}-panel-${tab.id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onSelect(tab.id)}
            onKeyDown={handleKeyDown}
          >
            {tab.label}
            {tab.count != null && <span className="panel-tabs__count">{tab.count}</span>}
          </button>
        )
      })}
    </div>
  )
}
