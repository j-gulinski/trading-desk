import { ROUTES, GROUP_ORDER } from '../routes/routes.js'

export default function Sidebar({ activePath }) {
  return (
    <nav className="sidebar">
      <div className="sidebar__brand">
        <div className="sidebar__brand-title">TRADING</div>
        <div className="sidebar__brand-sub">Microservices</div>
      </div>

      {GROUP_ORDER.map((group) => (
        <div className="sidebar__group" key={group}>
          <div className="sidebar__group-label">{group}</div>

          {ROUTES.filter((r) => r.group === group).map((route) => {
            const isActive = route.path === activePath
            return (
              <a
                key={route.path}
                href={`#/${route.path}`}
                className={
                  'sidebar__link' + (isActive ? ' sidebar__link--active' : '')
                }
              >
                <span className="sidebar__dot" />
                {route.label}
              </a>
            )
          })}
        </div>
      ))}

      <div className="sidebar__spacer" />
    </nav>
  )
}
