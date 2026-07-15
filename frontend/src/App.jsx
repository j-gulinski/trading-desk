import { useHashRoute } from './hooks/useHashRoute.js'
import { findRoute } from './routes/routes.js'
import AppShell from './layout/AppShell.jsx'

export default function App() {
  const path = useHashRoute()
  const route = findRoute(path)
  const Page = route.component

  return (
    <AppShell route={route}>
      <Page />
    </AppShell>
  )
}
