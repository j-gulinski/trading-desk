export default function PanelTabs({ tabs, activeId, onSelect }) {
  return (
    <div className="panel-tabs">
      {tabs.map((tab) => {
        const selected = tab.id === activeId
        return (
          <button
            key={tab.id}
            type="button"
            className={`panel-tabs__tab${selected ? ' panel-tabs__tab--active' : ''}`}
            onClick={() => onSelect(tab.id)}
          >
            {tab.label}
            {tab.count != null && <span className="panel-tabs__count">{tab.count}</span>}
          </button>
        )
      })}
    </div>
  )
}
