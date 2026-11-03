import { useEffect, useState } from 'react'
import { VideoOff } from 'lucide-react'
import { streamUrl, API_URL } from '../api'

// Modern browsers auto-upgrade http:// subresources to https:// on an https
// page, and silently fail to load when nothing answers on https (as is the
// case for the local-only API server). This is a known, permanent condition
// for this architecture (the video deliberately never leaves the demo PC),
// not a transient error - so it gets its own message instead of a useless
// "Retry" button.
const MIXED_CONTENT_BLOCKED =
  typeof window !== 'undefined' && window.location.protocol === 'https:' && API_URL.startsWith('http://')

/** MJPEG <img> stream with automatic reconnect on error/token-expiry. */
export function LiveVideo({ lane, className = '', refreshMs = 4 * 60 * 1000 }) {
  const [src, setSrc] = useState(null)
  const [failed, setFailed] = useState(false)
  const [nonce, setNonce] = useState(0)

  if (MIXED_CONTENT_BLOCKED) {
    return (
      <div className={`flex flex-col items-center justify-center gap-2 bg-slate-900 p-4 text-center text-slate-400 ${className}`}>
        <VideoOff size={28} />
        <p className="text-sm font-medium">Live video needs an insecure (http) connection to the local backend</p>
        <p className="max-w-xs text-xs opacity-80">
          This page is served over https, and the browser blocks it from loading the http video stream. View this
          page at <code className="font-mono">http://localhost:5173</code> (run <code className="font-mono">npm run dev</code> in{' '}
          <code className="font-mono">web/</code>) on the machine running the backend instead.
        </p>
      </div>
    )
  }

  useEffect(() => {
    let cancelled = false
    streamUrl(lane).then((url) => {
      if (!cancelled) {
        setSrc(url)
        setFailed(false)
      }
    })
    return () => {
      cancelled = true
    }
  }, [lane, nonce])

  // Periodically refresh the src so a short-lived auth token doesn't expire
  // mid-stream (the browser just reconnects to the new URL).
  useEffect(() => {
    const id = setInterval(() => setNonce((n) => n + 1), refreshMs)
    return () => clearInterval(id)
  }, [refreshMs])

  function retry() {
    setFailed(false)
    setNonce((n) => n + 1)
  }

  if (failed) {
    return (
      <div className={`flex flex-col items-center justify-center gap-2 bg-slate-900 text-slate-400 ${className}`}>
        <VideoOff size={28} />
        <p className="text-sm">Stream unavailable</p>
        <button onClick={retry} className="rounded bg-slate-800 px-3 py-1 text-xs hover:bg-slate-700">
          Retry
        </button>
      </div>
    )
  }

  return (
    <img
      key={nonce}
      src={src || undefined}
      onError={() => setFailed(true)}
      alt={`Live feed${lane ? ` - ${lane}` : ''}`}
      className={`bg-slate-900 object-cover ${className}`}
    />
  )
}
