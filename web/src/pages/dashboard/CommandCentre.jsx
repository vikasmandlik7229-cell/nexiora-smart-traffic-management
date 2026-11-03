import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { limit, orderBy } from '../../lib/query'
import {
  Ambulance,
  AlertTriangle,
  Car,
  CloudFog,
  LayoutGrid,
  ShieldAlert,
  TrendingDown,
} from 'lucide-react'
import { Area, CartesianGrid, ComposedChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useCollection } from '../../hooks/useCollection'
import { useDoc } from '../../hooks/useDoc'
import { useCountdown } from '../../hooks/useCountdown'
import { Card } from '../../components/Card'
import { StatCard } from '../../components/StatCard'
import { CongestionChip } from '../../components/CongestionChip'
import { Badge } from '../../components/Badge'
import { AlertItem } from '../../components/AlertItem'
import { CityMap, CityMapLegend } from '../../components/CityMap'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonCard } from '../../components/Skeleton'
import { SignalDots } from '../../components/SignalDots'
import { junctionPcu, congestionLevel, laneDirection, densityBarColor, localDateStr } from '../../lib/traffic'

const AQI_LABELS = { 1: 'Good', 2: 'Fair', 3: 'Moderate', 4: 'Poor', 5: 'Very Poor' }
const REQUEST_VARIANT = { approved: 'success', rejected: 'danger', pending: 'neutral' }

// A separate component (not inlined in .map()) because useCountdown is a
// hook - it must be called once per row, unconditionally, not from inside a
// callback passed to .map().
function SignalStatusRow({ junction, signal, pcu }) {
  const timeLeft = useCountdown(signal?.phaseEndsAt)
  return (
    <Link
      to={`/dashboard/junction/${junction.id}`}
      className="flex items-center justify-between gap-2 rounded-lg px-1.5 py-2 text-sm hover:bg-slate-50 dark:hover:bg-slate-800/60"
    >
      <span className="flex min-w-0 items-center gap-2">
        <SignalDots lanes={signal?.lanes} />
        <span className="truncate font-medium text-slate-700 dark:text-slate-200">{junction.id}</span>
      </span>
      <span className="shrink-0 text-xs text-slate-400">{timeLeft !== null ? `${timeLeft}s` : '-'}</span>
      <CongestionChip level={congestionLevel(pcu)} />
    </Link>
  )
}

export default function CommandCentre() {
  const { data: junctions, loading } = useCollection('junctions', [limit(10)])
  const { data: signals } = useCollection('signals', [limit(10)])
  const { data: liveCounts } = useCollection('live_counts', [limit(10)])
  const { data: roads } = useCollection('roads', [limit(30)])
  const { data: airQuality } = useCollection('air_quality', [limit(10)])
  const { data: accidents } = useCollection('accidents', [limit(20)])
  const { data: violations } = useCollection('violations', [limit(100)])
  const { data: metrics } = useCollection('metrics', [limit(20)])
  const { data: alerts } = useCollection('alerts', [orderBy('timestamp', 'desc'), limit(10)])
  const { data: requests } = useCollection('emergency_requests', [limit(10)])
  const { data: ambulance } = useDoc('emergency', 'active')
  const { data: j1 } = useDoc('junctions', 'J1')
  const { data: j1Counts } = useDoc('live_counts', 'J1')
  const { data: j1Short } = useDoc('short_predictions', 'J1')

  const signalByJunction = useMemo(() => Object.fromEntries(signals.map((s) => [s.id, s])), [signals])
  const countsByJunction = useMemo(() => Object.fromEntries(liveCounts.map((c) => [c.id, c])), [liveCounts])

  const activeAccidents = accidents.filter((a) => a.status === 'active')
  const totalVehicles = liveCounts.reduce((sum, c) => sum + junctionPcu(c), 0)

  const todayMetrics = metrics.filter((m) => m.id.endsWith(localDateStr()))
  const avgAdaptive = todayMetrics.length
    ? todayMetrics.reduce((sum, m) => sum + (m.avgWaitAdaptiveS || 0), 0) / todayMetrics.length
    : null
  const avgFixed = todayMetrics.length
    ? todayMetrics.reduce((sum, m) => sum + (m.avgWaitFixedS || 0), 0) / todayMetrics.length
    : null

  const violationsToday = violations.filter((v) => v.timestamp && localDateStr(new Date(v.timestamp * 1000)) === localDateStr())

  const avgAqi = airQuality.length
    ? airQuality.reduce((sum, a) => sum + (a.aqi || 0), 0) / airQuality.length
    : null

  const densityRows = useMemo(
    () =>
      Object.entries(j1Counts?.lanes || {}).map(([laneId, l]) => ({
        lane: laneId,
        direction: laneDirection(j1?.approaches, laneId),
        count: l.count || 0,
        pcu: l.pcu || 0,
      })),
    [j1Counts, j1],
  )

  const predictionChart = useMemo(() => {
    const lanes = Object.values(j1Short?.lanes || {}).filter((p) => !p.status)
    if (lanes.length === 0) return []
    const sum = (key) => lanes.reduce((s, p) => s + (p[key] || 0), 0)
    return [
      { label: 'Now', pcu: Math.round(sum('now')) },
      { label: '+5 min', pcu: Math.round(sum('in5')) },
      { label: '+10 min', pcu: Math.round(sum('in10')) },
    ]
  }, [j1Short])

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Four primary KPIs, per the command-centre design spec */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Total Vehicles Detected"
          value={totalVehicles}
          icon={Car}
          hint="PCU-weighted, across all junctions"
          info="A PCU-weighted total, not a raw count: car = 1, bike = 0.5, bus/truck = 3."
        />
        <StatCard
          label="Active Traffic Intersections"
          value={junctions.length}
          icon={LayoutGrid}
          hint={`${signals.length} reporting live signal state`}
        />
        <StatCard
          label="Average Vehicle Waiting Time"
          value={avgAdaptive !== null ? `${avgAdaptive.toFixed(0)}s` : '-'}
          icon={TrendingDown}
          accent="green"
          hint={avgFixed !== null ? `vs ${avgFixed.toFixed(0)}s on fixed-time` : 'today'}
          trend={
            avgAdaptive !== null && avgFixed > 0
              ? { direction: 'down', positive: true, label: `${Math.round(((avgFixed - avgAdaptive) / avgFixed) * 100)}% shorter than fixed-time` }
              : null
          }
        />
        <StatCard
          label="Active Emergency Vehicles"
          value={ambulance?.active ? 1 : 0}
          icon={Ambulance}
          accent={ambulance?.active ? 'red' : 'slate'}
          hint={ambulance?.active ? `${ambulance.vehicleId} en route` : 'none active'}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard
          label="Active accidents"
          value={activeAccidents.length}
          icon={AlertTriangle}
          accent={activeAccidents.length ? 'amber' : 'slate'}
        />
        <StatCard label="Violations today" value={violationsToday.length} icon={ShieldAlert} />
        <StatCard
          label="Air quality (avg)"
          value={avgAqi !== null ? AQI_LABELS[Math.round(avgAqi)] || '-' : '-'}
          icon={CloudFog}
          accent={avgAqi >= 4 ? 'red' : avgAqi >= 3 ? 'amber' : 'green'}
          hint={avgAqi !== null ? `AQI ${avgAqi.toFixed(1)}` : 'no data yet'}
        />
      </div>

      {/* Live map / density / signal status - mirrors the command-centre mockup's three-panel row */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        <Card title="Live Traffic Map" className="lg:col-span-2">
          {junctions.length === 0 ? (
            <EmptyState title="No junctions yet" hint="Run backend/db/seed.py to seed junction data." />
          ) : (
            <>
              <CityMap
                junctions={junctions}
                signals={signals}
                liveCounts={liveCounts}
                roads={roads}
                accidents={accidents}
                ambulance={ambulance}
                height="340px"
              />
              <div className="mt-3">
                <CityMapLegend />
              </div>
            </>
          )}
        </Card>

        <Card title="Traffic Density (J1, current)">
          {densityRows.length === 0 ? (
            <EmptyState title="No live count data yet" hint="Run backend/run_signals.py." />
          ) : (
            <div className="space-y-3">
              {densityRows.map((row) => {
                const pct = Math.min(100, (row.pcu / 25) * 100)
                return (
                  <div key={row.lane}>
                    <div className="mb-1 flex items-center justify-between text-xs">
                      <span className="font-medium text-slate-600 dark:text-slate-300">
                        {row.direction ? `${row.direction} (${row.lane})` : row.lane}
                      </span>
                      <span className="text-slate-400">{row.count} veh</span>
                    </div>
                    <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${densityBarColor(row.pcu)}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Card>

        <Card title="Traffic Signal Status" action={<Link to="/dashboard/map" className="text-xs font-medium text-accent-600 hover:underline dark:text-accent-400">View All</Link>}>
          {junctions.length === 0 ? (
            <EmptyState title="No junctions yet" />
          ) : (
            <div className="space-y-1">
              {junctions.map((j) => (
                <SignalStatusRow
                  key={j.id}
                  junction={j}
                  signal={signalByJunction[j.id]}
                  pcu={junctionPcu(countsByJunction[j.id])}
                />
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card
          title="AI Traffic Prediction - J1 (next 10 minutes)"
          action={<Link to="/dashboard/predictions" className="text-xs font-medium text-accent-600 hover:underline dark:text-accent-400">Full predictions</Link>}
        >
          {predictionChart.length === 0 ? (
            <EmptyState title="No short-term predictions yet" hint="Run backend/prediction/predict_short.py." />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <ComposedChart data={predictionChart}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-800" />
                <XAxis dataKey="label" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Area type="monotone" dataKey="pcu" name="Predicted PCU" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.2} strokeWidth={2} />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Recent Alerts" action={<Link to="/dashboard/accidents" className="text-xs font-medium text-accent-600 hover:underline dark:text-accent-400">View All</Link>}>
          {alerts.length === 0 ? (
            <EmptyState title="No alerts yet" />
          ) : (
            alerts.map((a) => <AlertItem key={a.id} alert={a} />)
          )}
        </Card>
      </div>

      <Card title="Live view - J1">
        <p className="mb-3 text-xs text-slate-400">The raw annotated camera feed - detection boxes, lane ROIs and the active signal, drawn in real time.</p>
        <Link to="/dashboard/junction/J1" className="text-sm font-medium text-accent-600 hover:underline dark:text-accent-400">
          Open Live Traffic Monitoring &rarr;
        </Link>
      </Card>

      <Card title="Recent emergency requests">
        <p className="mb-3 text-xs text-slate-400">
          Requests are validated automatically against the RFID registry within a couple of seconds - vision-based
          detection isn't trained yet (see CLAUDE.md T4), so there's no manual approval step to act on here.
        </p>
        {requests.length === 0 ? (
          <EmptyState title="No emergency requests yet" hint="Run backend/emergency/ambulance_sim.py to simulate one." />
        ) : (
          <ul className="space-y-2">
            {requests.map((r) => (
              <li key={r.id} className="flex items-center justify-between border-b border-slate-100 py-1.5 text-sm last:border-0 dark:border-slate-800">
                <span className="text-slate-600 dark:text-slate-300">
                  {r.vehicleId || 'unknown'} &rarr; {r.destinationJunction} <span className="text-slate-400">({r.source})</span>
                </span>
                <Badge variant={REQUEST_VARIANT[r.status] || 'neutral'}>{r.status}</Badge>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
