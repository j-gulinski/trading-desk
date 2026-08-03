import { useState } from 'react'
import Sidebar from './Sidebar.jsx'
import TopBar from './TopBar.jsx'
import NewTradeDialog from '../components/trades/NewTradeDialog.jsx'

export default function AppShell({ route, children }) {
  const [newTradeOpen, setNewTradeOpen] = useState(false)

  return (
    <div className="app-shell">
      <Sidebar activePath={route.path} />

      <div className="content">
        <TopBar route={route} onNewTrade={() => setNewTradeOpen(true)} />
        {children}
      </div>

      {newTradeOpen && <NewTradeDialog onClose={() => setNewTradeOpen(false)} />}
    </div>
  )
}
