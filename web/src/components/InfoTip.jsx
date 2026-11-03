import { useEffect, useRef, useState } from 'react'
import { Info } from 'lucide-react'

/** A small (i) icon that reveals a plain-language explanation on click/tap.
 * Click-to-toggle (not hover-only) so it works on touch devices, with
 * outside-click-to-close. Use next to any jargon term (PCU, AQI, adaptive
 * mode, etc.) so a first-time visitor never has to guess what it means. */
export function InfoTip({ children, label = 'What does this mean?' }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    function onClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  return (
    <span ref={ref} className="relative inline-flex">
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation()
          setOpen((o) => !o)
        }}
        aria-label={label}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full text-slate-400 transition-colors hover:text-accent-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-500"
      >
        <Info size={14} />
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute left-1/2 top-full z-50 mt-2 w-56 -translate-x-1/2 rounded-lg border border-slate-200 bg-white p-2.5 text-xs font-normal normal-case leading-snug text-slate-600 shadow-lg dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
        >
          {children}
        </span>
      )}
    </span>
  )
}
