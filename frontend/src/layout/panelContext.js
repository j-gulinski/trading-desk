import { createContext, createElement, useContext } from 'react'

export const PANEL_ID = {
  newTrade: 'new-trade',
  books: 'books',
  tradeDetail: 'trade-detail',
}

const PanelContext = createContext(null)

export function PanelProvider({ value, children }) {
  return createElement(PanelContext.Provider, { value }, children)
}

export function usePanelCoordinator() {
  const coordinator = useContext(PanelContext)
  if (coordinator == null) throw new Error('Panels must be used inside AppShell')
  return coordinator
}
