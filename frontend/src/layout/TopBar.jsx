export default function TopBar({ route }) {
  return (
    <header className="topbar">
      <div>
        <h1 className="topbar__title">{route.label}</h1>
        <div className="topbar__subtitle">{route.subtitle}</div>
      </div>

      <div className="topbar__actions">
        <button className="btn-primary" type="button">
          New trade
        </button>
      </div>
    </header>
  )
}
