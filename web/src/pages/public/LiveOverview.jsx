import { useMemo } from 'react'
import { limit, orderBy } from '../../lib/query'
import { Ambulance, AlertTriangle, Car, Info, Sparkles, TrendingDown } from 'lucide-react'
import { useCollection } from '../../hooks/useCollection'
import { useDoc } from '../../hooks/useDoc'
import { Card } from '../../components/Card'
import { StatCard } from '../../components/StatCard'
import { CongestionChip } from '../../components/CongestionChip'
import { ModeBadge } from '../../components/Badge'
import { AlertItem } from '../../components/AlertItem'
import { LiveVideo } from '../../components/LiveVideo'
import { InfoTip } from '../../components/InfoTip'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonCard } from '../../components/Skeleton'
import { SignalDots } from '../../components/SignalDots'
import { useCountdown } from '../../hooks/useCountdown'
import { congestionLevel, junctionPcu, localDateStr } from '../../lib/traffic'

// A separate component (not inlined in .map()) because useCountdown is a
// hook - it must be called once per card, unconditionally, not from inside
// a callback passed to .map().
function JunctionCard({ junction, signal, pcu, aqi }) {
  const timeLeft = useCountdown(signal?.phaseEndsAt)
  return (
    <Card className="transition-shadow hover:shadow-md">
      <div className="flex items-center justify-between">
        <span className="font-semibold text-slate-800 dark:text-white">{junction.id}</span>
        {signal && <ModeBadge mode={signal.mode} />}
      </div>
      <p className="mb-3 truncate text-xs text-slate-500 dark:text-slate-400">{junction.name}</p>
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5">
          <SignalDots lanes={signal?.lanes} />
          {timeLeft !== null && <span className="text-xs font-mono tabular-nums text-slate-500 dark:text-slate-400">{timeLeft}s</span>}
        </span>
        <div className="text-right">
          <CongestionChip level={congestionLevel(pcu)} />
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">PCU {pcu}</p>
          {aqi && <p className="text-xs text-slate-400">AQI {aqi.aqi} ({aqi.label})</p>}
        </div>
      </div>
    </Card>
  )
}

const PUBLIC_STREAM = true // mirrors backend config.PUBLIC_STREAM default
const AQI_LABELS = { 1: 'Good', 2: 'Fair', 3: 'Moderate', 4: 'Poor', 5: 'Very Poor' }

export default function LiveOverview() {
  const { data: junctions, loading: junctionsLoading } = useCollection('junctions', [limit(10)])
  const { data: signals } = useCollection('signals', [limit(10)])
  const { data: liveCounts } = useCollection('live_counts', [limit(10)])
  const { data: airQuality } = useCollection('air_quality', [limit(10)])
  const { data: accidents } = useCollection('accidents', [limit(20)])
  const { data: metrics } = useCollection('metrics', [limit(20)])
  const { data: alerts } = useCollection('alerts', [orderBy('timestamp', 'desc'), limit(8)])
  const { data: activeEmergency } = useDoc('emergency', 'active')

  const signalByJunction = useMemo(() => Object.fromEntries(signals.map((s) => [s.id, s])), [signals])
  const countsByJunction = useMemo(() => Object.fromEntries(liveCounts.map((c) => [c.id, c])), [liveCounts])
  const aqiByJunction = useMemo(() => Object.fromEntries(airQuality.map((a) => [a.id, a])), [airQuality])

  const publicAlerts = alerts.filter((a) => a.public)
  const activeAccidents = accidents.filter((a) => a.status === 'active')

  const totalVehicles = liveCounts.reduce((sum, c) => sum + junctionPcu(c), 0)

  const modeCounts = signals.reduce((acc, s) => {
    acc[s.mode] = (acc[s.mode] || 0) + 1
    return acc
  }, {})
  const modeSummary = Object.entries(modeCounts)
    .map(([mode, n]) => `${n} ${mode}`)
    .join(', ') || 'no signals reporting yet'

  const todayMetrics = metrics.filter((m) => m.id.endsWith(localDateStr()))
  const avgReduction =
    todayMetrics.length > 0
      ? todayMetrics.reduce((sum, m) => sum + (m.waitReductionPct || 0), 0) / todayMetrics.length
      : null

  const avgAqi = airQuality.length
    ? airQuality.reduce((sum, a) => sum + (a.aqi || 0), 0) / airQuality.length
    : null

  if (junctionsLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-3 rounded-xl border border-accent-200 bg-accent-50 p-4 dark:border-accent-500/20 dark:bg-accent-500/10">
        <Sparkles size={20} className="mt-0.5 shrink-0 text-accent-600 dark:text-accent-400" />
        <p className="text-sm text-slate-700 dark:text-slate-200">
          <span className="font-semibold">Smart Traffic AI</span> watches live traffic at <span className="font-semibold">J1</span> with
          an AI vehicle detector, automatically adjusts that junction's signal timing to match real demand, and tracks a
          wider simulated city network (J2-J4) to demonstrate ambulance priority, accident response and congestion
          prediction. Look for the small <Info size={12} className="inline -translate-y-0.5" /> icons next to technical
          terms for a plain-language explanation.
        </p>
      </div>

      {activeEmergency?.active && (
        <div className="flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white">
          <Ambulance size={18} className="animate-pulse" />
          Ambulance en route - priority corridor active
          {activeEmergency.nextJunctionId && ` - approaching ${activeEmergency.nextJunctionId}`}
        </div>
      )}
      {activeAccidents.slice(0, 3).map((a) => (
        <div key={a.id} className="flex items-center gap-2 rounded-lg bg-orange-500 px-4 py-2 text-sm font-semibold text-white">
          <AlertTriangle size={18} />
          Accident at {a.junctionId || a.roadId} ({a.severity}) - predicted delay {Math.round(a.predictedDelayMin || 0)} min
        </div>
      ))}
      {activeAccidents.length > 3 && (
        <p className="text-sm font-medium text-orange-500">+ {activeAccidents.length - 3} more active accident(s) - see the City Map or dashboard for the full list.</p>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Vehicles now"
          value={totalVehicles}
          icon={Car}
          hint="across all junctions"
          info="A PCU-weighted total, not a raw vehicle count: a car counts as 1, a bike as 0.5, a bus or truck as 3, since bigger vehicles take up more road space."
        />
        <StatCard
          label="Signal modes"
          value={signals.length}
          icon={TrendingDown}
          hint={modeSummary}
          info="Each junction runs one mode at a time: Adaptive (timing follows real traffic), Eco (shorter cycles when air quality is poor), Emergency (an ambulance has priority), Accident (a lane is blocked), Peak (anticipating a predicted busy spell), or Manual (a controller has taken over)."
        />
        <StatCard
          label="Avg wait reduction today"
          value={avgReduction !== null ? `${avgReduction.toFixed(0)}%` : '-'}
          icon={TrendingDown}
          hint="adaptive vs fixed-time"
          info="How much shorter today's average wait is with adaptive signal control, compared to a traditional fixed-time signal measured on the exact same traffic, side by side."
        />
        <StatCard
          label="Air quality (avg)"
          value={avgAqi !== null ? AQI_LABELS[Math.round(avgAqi)] || '-' : '-'}
          icon={AlertTriangle}
          accent={avgAqi >= 4 ? 'red' : avgAqi >= 3 ? 'amber' : 'green'}
          hint={avgAqi !== null ? `AQI ${avgAqi.toFixed(1)}` : 'no data yet'}
          info="Air Quality Index, 1 (Good) to 5 (Very Poor). At 4 or above, affected junctions switch to Eco mode automatically to cut down on vehicle idling."
        />
      </div>

      {PUBLIC_STREAM && (
        <Card title="Live view - J1">
          <LiveVideo lane={null} className="aspect-video w-full rounded-lg" />
        </Card>
      )}

      <div>
        <h2 className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-slate-600 dark:text-slate-300">
          Junctions
          <InfoTip>
            J1 has a real camera and real vehicle detection. J2-J4 have no camera - their traffic counts are simulated,
            so we can demonstrate a multi-junction city network without extra cameras. The small dots on each card are
            that junction's real lanes - one dot per lane, colored by its actual current light (not one single light,
            since a real junction always has some lanes red and one green at once).
          </InfoTip>
        </h2>
        {junctions.length === 0 ? (
          <EmptyState title="No junctions yet" hint="Run backend/db/seed.py to seed junction data." />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {junctions.map((j) => (
              <JunctionCard
                key={j.id}
                junction={j}
                signal={signalByJunction[j.id]}
                pcu={junctionPcu(countsByJunction[j.id])}
                aqi={aqiByJunction[j.id]}
              />
            ))}
          </div>
        )}
      </div>

      <Card
        title="Latest alerts"
        action={
          <InfoTip>
            Alerts appear automatically for ambulances, accidents, predicted congestion and poor air quality -
            nothing here is posted manually.
          </InfoTip>
        }
      >
        {publicAlerts.length === 0 ? (
          <EmptyState title="No alerts yet" hint="Alerts appear here once the backend pipeline (run_signals.py) is running." />
        ) : (
          publicAlerts.map((a) => <AlertItem key={a.id} alert={a} />)
        )}
      </Card>
    </div>
  )
}
