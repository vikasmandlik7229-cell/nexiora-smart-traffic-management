import { useEffect, useState } from 'react'

// Ticks locally so "Xs/Xm/Xh ago" labels keep advancing between Firestore
// snapshots - 'alerts' only gets new docs occasionally, so without a local
// tick this would freeze at whatever value it had at the last snapshot,
// the same frozen-display bug class as the signal countdown.
export function useRelativeTime(timestamp) {
  const [, forceTick] = useState(0)
  useEffect(() => {
    if (!timestamp) return undefined
    const id = setInterval(() => forceTick((n) => n + 1), 10_000)
    return () => clearInterval(id)
  }, [timestamp])

  if (!timestamp) return ''
  const seconds = Math.max(0, Math.round(Date.now() / 1000 - timestamp))
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`
  return `${Math.round(seconds / 86400)}d ago`
}
