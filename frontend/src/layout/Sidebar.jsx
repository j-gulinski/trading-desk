import { ROUTES, GROUP_ORDER } from '../routes/routes.js'
import RouteIcon from './RouteIcon.jsx'
import StreamsBadge from './StreamsBadge.jsx'

export default function Sidebar({ activePath, collapsed, onToggleCollapse }) {
  return (
    <nav
      className={`sidebar${collapsed ? ' sidebar--collapsed' : ''}`}
      aria-label="Primary navigation"
    >
      <div className="sidebar__brand">
        <div className="sidebar__brand-mark">
          <div className="sidebar__brand-title">TRADING</div>
          <div className="sidebar__brand-sub">Microservices</div>
        </div>
        <span className="sidebar__brand-compact" aria-hidden="true">TM</span>
        <button
          type="button"
          className="sidebar__collapse"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-pressed={collapsed}
          onClick={() => onToggleCollapse(!collapsed)}
        >
          {collapsed ? '»' : '«'}
        </button>
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
                className={'sidebar__link' + (isActive ? ' sidebar__link--active' : '')}
                aria-label={route.label}
                title={route.label}
                aria-current={isActive ? 'page' : undefined}
              >
                <RouteIcon path={route.path} />
                <span className="sidebar__label">{route.label}</span>
              </a>
            )
          })}
        </div>
      ))}

      <div className="sidebar__spacer" />
      <StreamsBadge />
    </nav>
  )
}
