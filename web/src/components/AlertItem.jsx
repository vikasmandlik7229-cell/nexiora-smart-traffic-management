import { AlertCircle, Ambulance, CloudFog, TrendingUp, ShieldAlert } from 'lucide-react'
import { useRelativeTime } from '../hooks/useRelativeTime'

const ICONS = {
  ambulance: Ambulance,
  emergency: Ambulance,
  accident: AlertCircle,
  violation: ShieldAlert,
  congestion: TrendingUp,
  prediction: TrendingUp,
  air: CloudFog,
  security: ShieldAlert,
}

const SEVERITY_DOT = {
  low: 'bg-slate-400',
  medium: 'bg-amber-500',
  high: 'bg-red-500',
}

export function AlertItem({ alert }) {
  const Icon = ICONS[alert.type] || AlertCircle
  const relativeTime = useRelativeTime(alert.timestamp)
  return (
    <div className="flex items-start gap-3 border-b border-slate-100 py-2.5 last:border-0 dark:border-slate-800">
      <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${SEVERITY_DOT[alert.severity] || SEVERITY_DOT.low}`} />
      <Icon size={16} className="mt-0.5 shrink-0 text-slate-400" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm text-slate-700 dark:text-slate-200">{alert.message}</p>
        <p className="text-xs text-slate-400">{relativeTime}</p>
      </div>
    </div>
  )
}
