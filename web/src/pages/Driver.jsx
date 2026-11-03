import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { limit, orderBy } from '../lib/query'
import { Ambulance, AlertTriangle, CheckCircle2, LogOut, Moon, Sun, TrafficCone, XCircle } from 'lucide-react'
import { logout } from '../lib/auth'
import { useAuth } from '../hooks/useAuth'
import { useTheme } from '../hooks/useTheme'
import { useDoc } from '../hooks/useDoc'
import { useCollection } from '../hooks/useCollection'
import { Card } from '../components/Card'
import { CityMap } from '../components/CityMap'
import { EmptyState } from '../components/EmptyState'
import { submitEmergencyRequest, requestEndTrip } from '../lib/emergency'

const KNOWN_VEHICLES = [
  { vehicleId: 'AMB001', tagId: 'RFID-AMB-001', label: 'AMB001 - City General Hospital' },
  { vehicleId: 'AMB002', tagId: 'RFID-AMB-002', label: 'AMB002 - St. Mary\'s Hospital' },
  { vehicleId: 'FIRE001', tagId: 'RFID-FIRE-001', label: 'FIRE001 - Fire Station 1' },
]

export default function Driver() {
  const { user, vehicleId: myVehicleId } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const navigate = useNavigate()
  const { data: junctions } = useCollection('junctions', [limit(10)])
  // Dispatch alerts targeted at this driver's own vehicle, sent
  // automatically when an accident is detected nearest to their base
  // (backend/accidents/manager.py's _notify_nearest_ambulance) - the
  // backend already filters this to only alerts meant for them.
  const { data: alerts } = useCollection('alerts', [orderBy('timestamp', 'desc'), limit(10)])
  const dispatchAlerts = alerts.filter((a) => a.type === 'dispatch')

  const [vehicleId, setVehicleId] = useState('')
  const [tagId, setTagId] = useState('')
  const [destination, setDestination] = useState('')
  const [requestId, setRequestId] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [endingTrip, setEndingTrip] = useState(false)

  // Once logged in, the system already knows which vehicle this driver is
  // linked to - no need to make them type or click to identify themselves.
  useEffect(() => {
    if (!myVehicleId || vehicleId) return
    const known = KNOWN_VEHICLES.find((v) => v.vehicleId === myVehicleId)
    if (known) pickKnown(known)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [myVehicleId])

  const { data: request } = useDoc('emergency_requests', requestId)
  const { data: ambulance } = useDoc('emergency', 'active')

  function handleLogout() {
    logout()
    navigate('/login')
  }

  function pickKnown(v) {
    setVehicleId(v.vehicleId)
    setTagId(v.tagId)
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    try {
      const id = await submitEmergencyRequest({ vehicleId, tagId, destinationJunction: destination })
      setRequestId(id)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleEndTrip() {
    setEndingTrip(true)
    try {
      await requestEndTrip(vehicleId)
    } finally {
      setEndingTrip(false)
    }
  }

  function reset() {
    setRequestId(null)
  }

  const tripActive = request?.status === 'approved' && ambulance?.active && ambulance.vehicleId === vehicleId

  return (
    <div className="mx-auto min-h-screen max-w-2xl px-4 py-6">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xl font-bold text-slate-900 dark:text-white">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent-600">
            <TrafficCone size={18} className="text-white" />
          </span>
          Ambulance Driver
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden text-sm text-slate-500 dark:text-slate-400 sm:inline">{user?.email}</span>
          <button onClick={toggleTheme} className="rounded-md p-2 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800">
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <button onClick={handleLogout} className="flex items-center gap-1 rounded-md px-2 py-1.5 text-sm text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800">
            <LogOut size={16} /> Logout
          </button>
        </div>
      </div>

      {dispatchAlerts.length > 0 && !requestId && (
        <div className="mb-4 space-y-2">
          {dispatchAlerts.map((a) => (
            <div key={a.id} className="flex items-start gap-2 rounded-lg bg-orange-500 px-4 py-2.5 text-sm font-medium text-white">
              <AlertTriangle size={18} className="mt-0.5 shrink-0" />
              <span>{a.message}</span>
            </div>
          ))}
        </div>
      )}

      {!requestId && (
        <Card title="Start an emergency trip">
          <p className="mb-4 text-xs text-slate-400">
            Your vehicle ID and RFID tag are checked against the authorised-vehicle registry before any signal gets
            pre-empted.
          </p>
          <div className="mb-4 flex flex-wrap gap-2">
            {KNOWN_VEHICLES.map((v) => (
              <button
                key={v.vehicleId}
                type="button"
                onClick={() => pickKnown(v)}
                className="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
              >
                {v.label}
              </button>
            ))}
          </div>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-200">Vehicle ID</label>
              <input
                required
                value={vehicleId}
                onChange={(e) => setVehicleId(e.target.value)}
                placeholder="e.g. AMB001"
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-white"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-200">RFID tag ID</label>
              <input
                required
                value={tagId}
                onChange={(e) => setTagId(e.target.value)}
                placeholder="e.g. RFID-AMB-001"
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-white"
              />
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
              className="flex w-full items-center justify-center gap-2 rounded-md bg-red-600 py-2.5 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60"
            >
              <Ambulance size={16} /> {submitting ? 'Submitting...' : 'Start Emergency Trip'}
            </button>
          </form>
        </Card>
      )}

      {requestId && request?.status === 'pending' && (
        <Card>
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <Ambulance size={32} className="animate-pulse text-accent-500" />
            <p className="font-medium text-slate-700 dark:text-slate-200">Waiting for approval...</p>
            <p className="text-xs text-slate-400">Validating {vehicleId} / {tagId} against the RFID registry.</p>
          </div>
        </Card>
      )}

      {requestId && request?.status === 'rejected' && (
        <Card>
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <XCircle size={32} className="text-red-500" />
            <p className="font-medium text-slate-700 dark:text-slate-200">Request rejected</p>
            <p className="text-sm text-slate-500 dark:text-slate-400">{request.reason}</p>
            <button onClick={reset} className="mt-2 rounded-md bg-slate-200 px-4 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-300 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700">
              Try again
            </button>
          </div>
        </Card>
      )}

      {requestId && request?.status === 'approved' && (
        <div className="space-y-4">
          <Card>
            <div className="mb-3 flex items-center gap-2 text-green-600 dark:text-green-400">
              <CheckCircle2 size={20} />
              <span className="font-semibold">Approved - {request.reason}</span>
            </div>
            {!tripActive ? (
              <EmptyState
                title="Waiting for the ambulance to start moving"
                hint="Run backend/emergency/ambulance_sim.py in a separate terminal - the web app only approves the trip, the GPS simulation runs there."
              />
            ) : (
              <>
                <div className="mb-3 grid grid-cols-2 gap-3 text-sm">
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
                <CityMap junctions={junctions} ambulance={ambulance} height="320px" />
              </>
            )}
            <button
              onClick={handleEndTrip}
              disabled={endingTrip}
              className="mt-4 w-full rounded-md bg-slate-200 py-2 text-sm font-medium text-slate-700 hover:bg-slate-300 disabled:opacity-60 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
            >
              {endingTrip ? 'Ending trip...' : 'End Trip'}
            </button>
          </Card>
        </div>
      )}
    </div>
  )
}
