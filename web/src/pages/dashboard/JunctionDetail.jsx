import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Gauge, Lock, Radio, Unlock } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useDoc } from '../../hooks/useDoc'
import { Card } from '../../components/Card'
import { LiveVideo } from '../../components/LiveVideo'
import { TrafficLight } from '../../components/TrafficLight'
import { ModeBadge } from '../../components/Badge'
import { CongestionChip } from '../../components/CongestionChip'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonCard } from '../../components/Skeleton'
import { congestionLevel, laneDirection, densityBarColor, CONGESTION_COLORS } from '../../lib/traffic'
import { submitCommand, MAX_OVERRIDE_SECONDS } from '../../lib/commands'

const CLASS_LABELS = { car: 'Cars', bike: 'Bikes', auto: 'Autos', bus: 'Buses', truck: 'Trucks' }
const CLASS_BAR_COLOR = { car: 'bg-accent-500', bike: 'bg-amber-500', auto: 'bg-purple-500', bus: 'bg-signal-green', truck: 'bg-signal-red' }

export default function JunctionDetail() {
  const { junctionId } = useParams()
  const { data: junction } = useDoc('junctions', junctionId)
  const { data: signal } = useDoc('signals', junctionId)
  const { data: liveCount } = useDoc('live_counts', junctionId)
  const { data: shortPredictions } = useDoc('short_predictions', junctionId)
  const { data: predictions } = useDoc('predictions', junctionId)

  const [overrideLane, setOverrideLane] = useState('')
  const [duration, setDuration] = useState(30)
  const [lastCommandId, setLastCommandId] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const { data: lastCommand } = useDoc('commands', lastCommandId)

  const lanes = signal?.lanes || {}
  const laneIds = Object.keys(lanes)
  const chartData = useMemo(
    () =>
      Object.entries(liveCount?.lanes || {}).map(([laneId, l]) => ({
        lane: laneId,
        count: l.count || 0,
        pcu: l.pcu || 0,
      })),
    [liveCount],
  )
  const totalPcu = chartData.reduce((sum, r) => sum + r.pcu, 0)

  const classTotals = useMemo(() => {
    const totals = {}
    Object.values(liveCount?.lanes || {}).forEach((l) => {
      Object.entries(l.byClass || {}).forEach(([cls, n]) => {
        totals[cls] = (totals[cls] || 0) + n
      })
    })
    return totals
  }, [liveCount])
  const totalVehicleCount = Object.values(classTotals).reduce((s, n) => s + n, 0)
  const maxClassCount = Math.max(1, ...Object.values(classTotals))
  const overallDensityPct = Math.min(100, Math.round((totalPcu / (4 * 25)) * 100))

  async function handleForceGreen() {
    if (!overrideLane) return
    setSubmitting(true)
    try {
      const id = await submitCommand(junctionId, 'force_green', {
        laneId: overrideLane,
        durationS: Math.min(duration, MAX_OVERRIDE_SECONDS),
      })
      setLastCommandId(id)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRelease() {
    setSubmitting(true)
    try {
      const id = await submitCommand(junctionId, 'release')
      setLastCommandId(id)
    } finally {
      setSubmitting(false)
    }
  }

  if (!junction) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Gauge size={20} className="text-accent-500" />
        <h1 className="text-xl font-bold text-slate-800 dark:text-white">{junction.id} - {junction.name}</h1>
        {signal && <ModeBadge mode={signal.mode} />}
        {junction.isVirtual && <span className="text-xs italic text-slate-400">virtual junction - simulated counts</span>}
      </div>

      {junctionId === 'J1' && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:col-span-2">
            {laneIds.length > 0 ? (
              laneIds.map((laneId) => {
                const l = liveCount?.lanes?.[laneId]
                const direction = laneDirection(junction.approaches, laneId)
                return (
                  <div key={laneId} className="overflow-hidden rounded-xl border border-slate-200 bg-slate-900 dark:border-slate-800">
                    <div className="relative aspect-video w-full">
                      <LiveVideo lane={laneId} className="h-full w-full" />
                      <span className="absolute left-2 top-2 flex items-center gap-1 rounded-full bg-black/60 px-2 py-0.5 text-[10px] font-semibold text-white">
                        <Radio size={10} className="animate-pulse text-red-400" /> LIVE
                      </span>
                      <span className="absolute right-2 top-2 rounded-full bg-black/60 px-2 py-0.5 text-[10px] font-medium text-white">
                        {laneId}{direction ? ` - ${direction}` : ''}
                      </span>
                    </div>
                    <div className="flex items-center justify-between bg-slate-800 px-2.5 py-1.5 text-xs text-slate-300">
                      <span>{l?.count ?? 0} vehicles</span>
                      <span>{(l?.pcu ?? 0).toFixed(1)} PCU</span>
                    </div>
                  </div>
                )
              })
            ) : (
              <div className="sm:col-span-2">
                <Card title="Live view">
                  <LiveVideo lane={null} className="aspect-video w-full rounded-lg" />
                </Card>
              </div>
            )}
          </div>

          <div className="space-y-4">
            <Card title="Vehicle Count (live)">
              {totalVehicleCount === 0 ? (
                <EmptyState title="No live count data yet" hint="Run backend/run_signals.py." />
              ) : (
                <div className="space-y-2.5">
                  {Object.entries(classTotals).map(([cls, n]) => (
                    <div key={cls}>
                      <div className="mb-1 flex items-center justify-between text-xs">
                        <span className="font-medium text-slate-600 dark:text-slate-300">{CLASS_LABELS[cls] || cls}</span>
                        <span className="text-slate-400">{n}</span>
                      </div>
                      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                        <div
                          className={`h-full rounded-full ${CLASS_BAR_COLOR[cls] || 'bg-accent-500'}`}
                          style={{ width: `${(n / maxClassCount) * 100}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card title="Overall Density">
              <div className="flex flex-col items-center justify-center gap-2 py-2">
                <div className="relative flex h-28 w-28 items-center justify-center rounded-full border-8 border-slate-100 dark:border-slate-800">
                  <div
                    className="absolute inset-0 rounded-full"
                    style={{
                      background: `conic-gradient(${CONGESTION_COLORS[congestionLevel(totalPcu)]} ${overallDensityPct * 3.6}deg, transparent 0deg)`,
                      mask: 'radial-gradient(farthest-side, transparent calc(100% - 8px), #000 calc(100% - 8px))',
                      WebkitMask: 'radial-gradient(farthest-side, transparent calc(100% - 8px), #000 calc(100% - 8px))',
                    }}
                  />
                  <span className="text-xl font-bold text-slate-800 dark:text-white">{overallDensityPct}%</span>
                </div>
                <CongestionChip level={congestionLevel(totalPcu)} />
              </div>
            </Card>
          </div>
        </div>
      )}

      {!signal ? (
        <EmptyState title="No live signal data" hint="Run backend/run_signals.py (J1) or backend/signals/virtual_junctions.py (others)." />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {laneIds.map((laneId) => (
            <Card key={laneId} className="flex flex-col items-center gap-2">
              <span className="font-semibold text-slate-700 dark:text-slate-200">{laneId}</span>
              <TrafficLight
                state={lanes[laneId].state}
                phaseEndsAt={laneId === signal.activeLane ? signal.phaseEndsAt : null}
                size="md"
              />
              <span className="text-xs text-slate-500 dark:text-slate-400">
                Load: {Math.round(lanes[laneId].load ?? 0)} PCU
              </span>
            </Card>
          ))}
        </div>
      )}

      <Card title="Traffic Density Monitoring">
        {chartData.length === 0 ? (
          <EmptyState title="No live count data yet" hint="Run backend/run_signals.py to feed detection into this junction." />
        ) : (
          <div className="space-y-3">
            {chartData.map((row) => {
              const direction = laneDirection(junction.approaches, row.lane)
              const pct = Math.min(100, (row.pcu / 25) * 100)
              return (
                <div key={row.lane}>
                  <div className="mb-1 flex items-center justify-between text-xs">
                    <span className="font-medium text-slate-600 dark:text-slate-300">
                      {direction ? `${direction} Lane (${row.lane})` : row.lane}
                    </span>
                    <span className="text-slate-400">{row.count} vehicles - {row.pcu.toFixed(1)} PCU</span>
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

      <Card title="Lane counts and PCU">
        {chartData.length === 0 ? (
          <EmptyState title="No live count data yet" hint="Run backend/run_signals.py to feed detection into this junction." />
        ) : (
          <>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-800" />
                <XAxis dataKey="lane" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="count" name="Raw count" fill="#94a3b8" radius={[4, 4, 0, 0]} />
                <Bar dataKey="pcu" name="PCU (weighted)" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <p className="mt-2 text-xs text-slate-400">
              Total load: {totalPcu} PCU - <CongestionChip level={congestionLevel(totalPcu)} />
            </p>
          </>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title="Next 5 / 10 minutes">
          {!shortPredictions?.lanes ? (
            <EmptyState title="No short-term predictions" hint="Only J1's real lanes are predicted (predict_short.py)." />
          ) : (
            <div className="grid grid-cols-2 gap-3">
              {Object.entries(shortPredictions.lanes).map(([laneId, p]) => (
                <div key={laneId} className="rounded-lg border border-slate-200 p-2 text-center dark:border-slate-800">
                  <p className="text-xs font-medium text-slate-600 dark:text-slate-300">{laneId}</p>
                  {p.status ? (
                    <p className="text-xs text-slate-400">{p.status}</p>
                  ) : (
                    <p className="text-sm text-slate-700 dark:text-slate-200">
                      {Math.round(p.now)} &rarr; {Math.round(p.in5)} &rarr; {Math.round(p.in10)}
                    </p>
                  )}
                  {p.level && <CongestionChip level={p.level} />}
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Peak hours (next 24h)">
          {!predictions?.peakHours?.length ? (
            <EmptyState title="No peak-hour predictions yet" hint="Run backend/prediction/predict_peak.py." />
          ) : (
            <ul className="space-y-1 text-sm text-slate-600 dark:text-slate-300">
              {predictions.peakHours.slice(0, 6).map((h) => (
                <li key={h}>{new Date(h).toLocaleString([], { weekday: 'short', hour: '2-digit' })}</li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Manual override">
        <p className="mb-3 text-xs text-slate-400">
          Force a lane green for up to {MAX_OVERRIDE_SECONDS}s, or release back to adaptive control. Safety rules
          (yellow-before-red, single green at a time) are enforced by the backend regardless of this override.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">Lane</label>
            <select
              value={overrideLane}
              onChange={(e) => setOverrideLane(e.target.value)}
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            >
              <option value="">Select lane</option>
              {laneIds.map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">Duration (s)</label>
            <input
              type="number"
              min={5}
              max={MAX_OVERRIDE_SECONDS}
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              className="w-24 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            />
          </div>
          <button
            onClick={handleForceGreen}
            disabled={!overrideLane || submitting}
            className="flex items-center gap-1.5 rounded-md bg-accent-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-accent-700 disabled:opacity-50"
          >
            <Lock size={14} /> Force green
          </button>
          <button
            onClick={handleRelease}
            disabled={submitting}
            className="flex items-center gap-1.5 rounded-md bg-slate-200 px-4 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-300 disabled:opacity-50 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
          >
            <Unlock size={14} /> Release
          </button>
        </div>
        {lastCommand && (
          <p className="mt-3 text-sm">
            Command <span className="font-mono text-xs">{lastCommandId}</span>:{' '}
            <span
              className={
                lastCommand.status === 'done'
                  ? 'font-semibold text-green-600 dark:text-green-400'
                  : lastCommand.status === 'rejected'
                    ? 'font-semibold text-red-600 dark:text-red-400'
                    : 'font-semibold text-amber-600 dark:text-amber-400'
              }
            >
              {lastCommand.status}
            </span>
            {lastCommand.reason && <span className="text-slate-400"> - {lastCommand.reason}</span>}
          </p>
        )}
      </Card>
    </div>
  )
}
