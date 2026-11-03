const LEVELS = {
  low: 'bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-300',
  medium: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',
  high: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300',
}

export function CongestionChip({ level }) {
  const key = String(level || '').toLowerCase()
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${LEVELS[key] || LEVELS.low}`}>
      {key ? key.charAt(0).toUpperCase() + key.slice(1) : 'Unknown'}
    </span>
  )
}
