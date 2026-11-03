import { useEffect, useState } from 'react'
import { ImageOff } from 'lucide-react'
import { evidenceUrl } from '../api'

/** Resolves a token-bearing evidence image URL from the local API
 * (backend/api/server.py's /api/evidence/{kind}/{filename}) and renders it,
 * or a graceful placeholder when there's no file to show. */
export function EvidenceImage({ kind, filename, className = 'h-32 w-full rounded-lg object-cover' }) {
  const [src, setSrc] = useState(null)

  useEffect(() => {
    let cancelled = false
    if (filename) evidenceUrl(kind, filename).then((url) => !cancelled && setSrc(url))
    return () => {
      cancelled = true
    }
  }, [kind, filename])

  if (!filename) {
    return (
      <div className={`flex flex-col items-center justify-center gap-1 bg-slate-100 text-slate-400 dark:bg-slate-800 ${className}`}>
        <ImageOff size={20} />
        <span className="text-xs">No evidence image</span>
      </div>
    )
  }
  return <img src={src} alt="Evidence" className={className} />
}
