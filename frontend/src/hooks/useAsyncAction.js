import { useState } from 'react'

export function useAsyncAction() {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState(null)

  async function run(action, formatError = (err) => err) {
    setPending(true)
    setError(null)
    try {
      await action()
      return true
    } catch (err) {
      setError(formatError(err))
      return false
    } finally {
      setPending(false)
    }
  }

  return { pending, error, run, clearError: () => setError(null), setError }
}
