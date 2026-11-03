import { useMemo, useState } from 'react'
import { orderBy, limit } from '../../lib/query'
import { Bell } from 'lucide-react'
import { useCollection } from '../../hooks/useCollection'
import { Card } from '../../components/Card'
import { AlertItem } from '../../components/AlertItem'
import { InfoTip } from '../../components/InfoTip'
import { EmptyState } from '../../components/EmptyState'
import { Skeleton } from '../../components/Skeleton'

const TYPES = ['all', 'ambulance', 'accident', 'congestion', 'prediction', 'air', 'security']

export default function Alerts() {
  const { data: alerts, loading } = useCollection('alerts', [orderBy('timestamp', 'desc'), limit(100)])
  const [filter, setFilter] = useState('all')

  const publicAlerts = useMemo(() => alerts.filter((a) => a.public), [alerts])
  const filtered = useMemo(
    () => (filter === 'all' ? publicAlerts : publicAlerts.filter((a) => a.type === filter)),
    [publicAlerts, filter],
  )

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Bell size={20} className="text-accent-500" />
        <h1 className="text-xl font-bold text-slate-800 dark:text-white">Public Alerts</h1>
        <InfoTip>
          Every alert is generated automatically by a backend event - an ambulance trip starting, an accident being
          detected, a lane predicted to get busy, or air quality turning poor. None of these are posted manually.
        </InfoTip>
      </div>

      <div className="flex flex-wrap gap-2">
        {TYPES.map((t) => (
          <button
            key={t}
            onClick={() => setFilter(t)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium capitalize transition-colors ${
              filter === t
                ? 'bg-accent-600 text-white'
                : 'bg-white text-slate-600 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <Card>
        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No alerts yet"
            hint="Alerts appear here once the backend detects congestion, ambulances, accidents, predictions or air-quality events."
          />
        ) : (
          <div>
            {filtered.map((a) => (
              <AlertItem key={a.id} alert={a} />
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
