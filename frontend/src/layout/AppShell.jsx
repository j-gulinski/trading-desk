import { useCallback, useMemo, useState } from 'react'
import Sidebar from './Sidebar.jsx'
import TopBar from './TopBar.jsx'
import NewTradePanel from '../components/trades/NewTradePanel.jsx'
import { useStoredFlag } from '../hooks/useStoredFlag.js'
import { STORAGE_KEYS } from '../config/storage.js'
import { PANEL_ID, PanelProvider } from './panelContext.js'

export default function AppShell({ route, children }) {
  const [activePanel, setActivePanel] = useState(null)
  const [collapsed, setCollapsed] = useStoredFlag(STORAGE_KEYS.sidebarCollapsed)
  const openPanel = useCallback((panelId) => setActivePanel(panelId), [])
  const closePanel = useCallback(
    (panelId) => setActivePanel((current) => (current === panelId ? null : current)),
    [],
  )
  const panels = useMemo(
    () => ({ activePanel, openPanel, closePanel }),
    [activePanel, openPanel, closePanel],
  )

  return (
    <PanelProvider value={panels}>
      <div className="app-shell">
        <Sidebar activePath={route.path} collapsed={collapsed} onToggleCollapse={setCollapsed} />

        <div className="content">
          <TopBar route={route} onNewTrade={() => openPanel(PANEL_ID.newTrade)} />
          {children}
          {activePanel === PANEL_ID.newTrade && (
            <NewTradePanel onClose={() => closePanel(PANEL_ID.newTrade)} />
          )}
        </div>
      </div>
    </PanelProvider>
  )
}
