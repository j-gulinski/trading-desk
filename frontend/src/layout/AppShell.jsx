import Sidebar from './Sidebar.jsx'
import TopBar from './TopBar.jsx'

export default function AppShell({ route, children }) {
  return (
    <div className="app-shell">
      <Sidebar activePath={route.path} />

      <div className="content">
        <TopBar route={route} />
        {children}
      </div>
    </div>
  )
}
