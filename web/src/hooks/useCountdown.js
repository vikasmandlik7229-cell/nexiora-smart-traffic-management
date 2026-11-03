import { useEffect, useState } from 'react'

// Ticks locally every 500ms so a countdown keeps moving between Firestore
// snapshots - signals only write on phase change (write-budget discipline),
// so without a local tick the displayed time would freeze between changes.
export function useCountdown(phaseEndsAt) {
  const [remaining, setRemaining] = useState(null)
  useEffect(() => {
    if (!phaseEndsAt) {
      setRemaining(null)
      return undefined
    }
    const tick = () => setRemaining(Math.max(0, Math.round(phaseEndsAt - Date.now() / 1000)))
    tick()
    const id = setInterval(tick, 500)
    return () => clearInterval(id)
  }, [phaseEndsAt])
  return remaining
}
