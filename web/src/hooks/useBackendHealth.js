import { useEffect, useState } from 'react'
import { checkHealth } from '../api'

/** Polls the local FastAPI backend's /api/health so layouts can show a
 * "Backend offline" banner when the Python backend isn't running. */
export function useBackendHealth(intervalMs = 15000) {
  const [healthy, setHealthy] = useState(null) // null = not checked yet

  useEffect(() => {
    let cancelled = false
    async function check() {
      try {
        await checkHealth()
        if (!cancelled) setHealthy(true)
      } catch {
        if (!cancelled) setHealthy(false)
      }
    }
    check()
    const id = setInterval(check, intervalMs)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [intervalMs])

  return healthy
}
