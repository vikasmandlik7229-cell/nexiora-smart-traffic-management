import { useMemo, useState } from 'react'
import { limit } from '../../lib/query'
import { Ambulance, CheckCircle2, Clock, XCircle } from 'lucide-react'
import { useCollection } from '../../hooks/useCollection'
import { useDoc } from '../../hooks/useDoc'
import { Card } from '../../components/Card'
import { CityMap } from '../../components/CityMap'
import { Badge } from '../../components/Badge'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonCard } from '../../components/Skeleton'
import { submitEmergencyRequest, requestEndTrip } from '../../lib/emergency'

const STATUS_ICON = { approved: CheckCircle2, rejected: XCircle, pending: Clock }
const STATUS_VARIANT = { approved: 'success', rejected: 'danger', pending: 'neutral' }

function fmtTime(sec) {
  if (!sec) return '-'
  return new Date(sec * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function Emergencies() {
  const { data: junctions, loading } = useCollection('junctions', [limit(10)])
  const { data: vehicles } = useCollection('authorised_vehicles', [limit(20)])
  const { data: requests } = useCollection('emergency_requests', [limit(10)])
  const { data: trips } = useCollection('emergency_trips', [limit(20)])
  const { data: ambulance } = useDoc('emergency', 'active')

  const [selectedVehicle, setSelectedVehicle] = useState('')
  const [destination, setDestination] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [ending, setEnding] = useState(false)

  const vehicle = vehicles.find((v) => v.id === selectedVehicle)

  async function handleStart(e) {
    e.preventDefault()
    if (!vehicle) return
    setSubmitting(true)
    try {
      await submitEmergencyRequest({ vehicleId: vehicle.id, tagId: vehicle.tagId, destinationJunction: destination, source: 'dashboard' })
    } finally {
      setSubmitting(false)
    }
  }

  async function handleEnd() {
    if (!ambulance?.vehicleId) return
    setEnding(true)
    try {
      await requestEndTrip(ambulance.vehicleId)
    } finally {
      setEnding(false)
    }
  }

  const avgTravelTime = useMemo(() => {
    const withTime = trips.filter((t) => t.travelTimeS)
    if (!withTime.length) return null
    return withTime.reduce((sum, t) => sum + t.travelTimeS, 0) / withTime.length
  }, [trips])

  if (loading) {
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
        <Ambulance size={20} className="text-accent-500" />
        <h1 className="text-xl font-bold text-slate-800 dark:text-white">Emergencies</h1>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title="Start an emergency">
          {vehicles.length === 0 ? (
            <EmptyState title="No authorised vehicles" hint="Run backend/db/seed.py, or add one in Settings." />
          ) : (
            <form onSubmit={handleStart} className="space-y-3">
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-200">Vehicle</label>
                <select
                  required
                  value={selectedVehicle}
                  onChange={(e) => setSelectedVehicle(e.target.value)}
                  className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                >
                  <option value="">Select vehicle</option>
                  {vehicles.map((v) => (
                    <option key={v.id} value={v.id} disabled={!v.active}>
                      {v.id} - {v.type} {v.active ? '' : '(inactive)'}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-200">Destination junction</label>
                <select
                  required
                  value={destination}
                  onChange={(e) => setDestination(e.target.value)}
                  className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                >
                  <option value="">Select destination</option>
                  {junctions.map((j) => (
                    <option key={j.id} value={j.id}>{j.id} - {j.name}</option>
                  ))}
                </select>
              </div>
              <button
                type="submit"
                disabled={submitting}
                className="flex w-full items-center justify-center gap-2 rounded-md bg-red-600 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60"
              >
                <Ambulance size={16} /> {submitting ? 'Starting...' : 'Start Emergency Trip'}
              </button>
            </form>
          )}
        </Card>

        <Card title="Active trip">
          {!ambulance?.active ? (
            <EmptyState title="No active emergency trip" />
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span className="font-semibold text-slate-700 dark:text-slate-200">{ambulance.vehicleId}</span>
                <Badge variant="emergency">ACTIVE</Badge>
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <p className="text-xs text-slate-400">Next junction</p>
                  <p className="font-semibold text-slate-700 dark:text-slate-200">{ambulance.nextJunctionId || '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-400">ETA</p>
                  <p className="font-semibold text-slate-700 dark:text-slate-200">
                    {ambulance.etaNextS != null ? `${Math.round(ambulance.etaNextS)}s` : '-'}
                  </p>
                </div>
              </div>
              <p className="text-xs text-slate-400">Pre-empted: {(ambulance.preempted || []).join(', ') || 'none yet'}</p>
              {ambulance.lat != null && <CityMap junctions={junctions} ambulance={ambulance} height="260px" />}
              <button
                onClick={handleEnd}
                disabled={ending}
                className="w-full rounded-md bg-slate-200 py-2 text-sm font-medium text-slate-700 hover:bg-slate-300 disabled:opacity-60 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
              >
                {ending ? 'Ending trip...' : 'End Trip'}
              </button>
            </div>
          )}
        </Card>
      </div>

      <Card title="Recent requests">
        {requests.length === 0 ? (
          <EmptyState title="No emergency requests yet" />
        ) : (
          <ul className="space-y-2">
            {requests.map((r) => {
              const Icon = STATUS_ICON[r.status] || Clock
              return (
                <li key={r.id} className="flex items-center justify-between border-b border-slate-100 py-1.5 text-sm last:border-0 dark:border-slate-800">
                  <span className="flex items-center gap-2 text-slate-600 dark:text-slate-300">
                    <Icon size={14} /> {r.vehicleId || 'unknown'} &rarr; {r.destinationJunction} ({r.source})
                  </span>
                  <Badge variant={STATUS_VARIANT[r.status] || 'neutral'}>{r.status}</Badge>
                </li>
              )
            })}
          </ul>
        )}
      </Card>

      <Card title="Trip history">
        {trips.length === 0 ? (
          <EmptyState title="No completed trips yet" hint="Run backend/emergency/ambulance_sim.py to simulate one." />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-slate-400">
                  <tr>
                    <th className="py-1.5 pr-4">Vehicle</th>
                    <th className="py-1.5 pr-4">Started</th>
                    <th className="py-1.5 pr-4">Travel time</th>
                    <th className="py-1.5 pr-4">Junctions pre-empted</th>
                    <th className="py-1.5">Outcome</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {trips.map((t) => (
                    <tr key={t.id}>
                      <td className="py-1.5 pr-4 font-medium text-slate-700 dark:text-slate-200">{t.vehicleId}</td>
                      <td className="py-1.5 pr-4 text-slate-500 dark:text-slate-400">{fmtTime(t.startedAt)}</td>
                      <td className="py-1.5 pr-4">{t.travelTimeS ? `${Math.round(t.travelTimeS)}s` : '-'}</td>
                      <td className="py-1.5 pr-4">{(t.junctionsPreempted || []).length}</td>
                      <td className="py-1.5">{t.endedEarly ? 'Ended early' : 'Completed'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {avgTravelTime !== null && (
              <p className="mt-3 text-xs text-slate-400">Average travel time: {avgTravelTime.toFixed(0)}s across {trips.length} trips.</p>
            )}
          </>
        )}
        <p className="mt-3 border-t border-slate-100 pt-3 text-xs text-slate-400 dark:border-slate-800">
          "Time saved" needs a paired with/without-corridor comparison, which isn't something a single live trip can
          measure. For that, run <code className="font-mono">python -m emergency.corridor_evaluator --trials 20</code> -
          it prints the average and saves a chart to <code className="font-mono">backend/training/reports/corridor_time_saved.png</code>.
        </p>
      </Card>
    </div>
  )
}
