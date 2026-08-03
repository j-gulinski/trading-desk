export default function TopBar({ route, onNewTrade }) {
  return (
    <header className="topbar">
      <div>
        <h1 className="topbar__title">{route.label}</h1>
        <div className="topbar__subtitle">{route.subtitle}</div>
      </div>
      <button type="button" className="topbar__action" onClick={onNewTrade}>
        New trade
      </button>
    </header>
  )
}
