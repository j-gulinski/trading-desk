import { useEffect, useState } from 'react'
import { getStatus } from './services/api.js'

export default function App() {
  const [status, setStatus] = useState(null)

  useEffect(() => {
    let timeout
    async function load() {
      try {
        setStatus(await getStatus())
      } catch {
        setStatus({ 'monitoring-service': { status: 'DOWN' } })
      } finally {
        timeout = setInterval(load, 2000)
      }
    }

    load()

    return () => clearInterval(timeout)
  }, [])

  if (!status) return <p>checking…</p>

  return (
    <main>
      <h1>System Health</h1>
      <ul>
        {Object.entries(status).map(([name, info]) => (
          <li key={name}>
            <strong>{name}</strong>: {info.status}
            {info.response_time_ms != null && ` — ${info.response_time_ms} ms`}
          </li>
        ))}
      </ul>
    </main>
  )
}
