import { TrendingDown, TrendingUp } from 'lucide-react'
import { Card } from './Card'
import { InfoTip } from './InfoTip'

// Tailwind's compiler only picks up complete, literal class strings, so
// dynamically interpolated classes (e.g. `bg-${accent}-100`) silently
// produce no CSS - a static lookup map is required instead.
const ICON_STYLES = {
  accent: 'bg-accent-100 text-accent-600 dark:bg-accent-500/10 dark:text-accent-400',
  green: 'bg-green-100 text-green-600 dark:bg-green-500/10 dark:text-green-400',
  red: 'bg-red-100 text-red-600 dark:bg-red-500/10 dark:text-red-400',
  amber: 'bg-amber-100 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400',
  slate: 'bg-slate-100 text-slate-600 dark:bg-slate-500/10 dark:text-slate-400',
}

export function StatCard({ label, value, icon: Icon, hint, accent = 'accent', info, trend }) {
  return (
    <Card className="flex items-start justify-between transition-shadow hover:shadow-md">
      <div>
        <p className="flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
          {label}
          {info && <InfoTip>{info}</InfoTip>}
        </p>
        <p className="mt-1 text-2xl font-bold text-slate-900 dark:text-white">{value}</p>
        {trend && (
          <p className={`mt-1 flex items-center gap-1 text-xs font-semibold ${trend.positive ? 'text-green-600 dark:text-green-400' : 'text-slate-500 dark:text-slate-400'}`}>
            {trend.direction === 'down' ? <TrendingDown size={12} /> : <TrendingUp size={12} />}
            {trend.label}
          </p>
        )}
        {hint && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
      </div>
      {Icon && (
        <div className={`rounded-lg p-2 ${ICON_STYLES[accent] || ICON_STYLES.accent}`}>
          <Icon size={20} />
        </div>
      )}
    </Card>
  )
}
