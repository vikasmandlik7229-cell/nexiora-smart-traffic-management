// Static map (see StatCard.jsx for why this must be static, not interpolated).
const VARIANTS = {
  adaptive: 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300',
  peak: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',
  eco: 'bg-teal-100 text-teal-700 dark:bg-teal-500/15 dark:text-teal-300',
  emergency: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300 animate-pulse',
  accident: 'bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-300',
  manual: 'bg-purple-100 text-purple-700 dark:bg-purple-500/15 dark:text-purple-300',
  neutral: 'bg-slate-100 text-slate-700 dark:bg-slate-500/15 dark:text-slate-300',
  success: 'bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-300',
  danger: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300',
}

export function Badge({ children, variant = 'neutral', className = '' }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${VARIANTS[variant] || VARIANTS.neutral} ${className}`}
    >
      {children}
    </span>
  )
}

export function ModeBadge({ mode }) {
  const variant = VARIANTS[mode] ? mode : 'neutral'
  return <Badge variant={variant}>{String(mode || 'unknown').toUpperCase()}</Badge>
}
