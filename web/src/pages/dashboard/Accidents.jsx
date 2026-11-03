import { useState } from 'react'
import { limit } from '../../lib/query'
import { AlertTriangle } from 'lucide-react'
import { useCollection } from '../../hooks/useCollection'
import { Card } from '../../components/Card'
import { CityMap } from '../../components/CityMap'
import { Badge } from '../../components/Badge'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonCard } from '../../components/Skeleton'
import { EvidenceImage } from '../../components/EvidenceImage'
import { reportAccident, markAccidentResolving } from '../../lib/accidents'

const SEVERITY_VARIANT = { low: 'neutral', medium: 'amber', high: 'danger', critical: 'danger' }

function fmtTime(sec) {
  if (!sec) return '-'
  return new Date(sec * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function Accidents() {
  const { data: junctions, loading } = useCollection('junctions', [limit(10)])
  const { data: signals } = useCollection('signals', [limit(10)])
  const { data: accidents } = useCollection('accidents', [limit(30)])

  const [junctionId, setJunctionId] = useState('')
  const [laneId, setLaneId] = useState('')
  const [severity, setSeverity] = useState('medium')
  const [arrivalRate, setArrivalRate] = useState(6)
  const [submitting, setSubmitting] = useState(false)
  const [resolvingId, setResolvingId] = useState(null)

  const activeAccidents = accidents.filter((a) => a.status === 'active' || a.status === 'resolving')
  const resolvedAccidents = accidents.filter((a) => a.status === 'resolved')
  const selectedSignal = signals.find((s) => s.id === junctionId)
  const laneOptions = Object.keys(selectedSignal?.lanes || {})

  async function handleReport(e) {
    e.preventDefault()
    setSubmitting(true)
    try {
      await reportAccident({ junctionId, laneId: laneId || null, severity, arrivalRatePcuPerMin: Number(arrivalRate) })
      setLaneId('')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleResolve(id) {
    setResolvingId(id)
    try {
      await markAccidentResolving(id)
    } finally {
      setResolvingId(null)
    }
  }

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
        <AlertTriangle size={20} className="text-accent-500" />
        <h1 className="text-xl font-bold text-slate-800 dark:text-white">Accidents</h1>
      </div>

      <Card title="Report an accident">
        <p className="mb-3 text-xs text-slate-400">
          For demos or junctions without a camera feed. Vision-detected accidents at J1 are created automatically.
        </p>
        <form onSubmit={handleReport} className="grid grid-cols-1 gap-3 sm:grid-cols-4 sm:items-end">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">Junction</label>
            <select
              required
              value={junctionId}
              onChange={(e) => { setJunctionId(e.target.value); setLaneId('') }}
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            >
              <option value="">Select</option>
              {junctions.map((j) => (
                <option key={j.id} value={j.id}>{j.id}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">Lane (optional)</label>
            <select
              value={laneId}
              onChange={(e) => setLaneId(e.target.value)}
              disabled={laneOptions.length === 0}
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            >
              <option value="">None</option>
              {laneOptions.map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">Severity</label>
            <select
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            >
              {['low', 'medium', 'high', 'critical'].map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            disabled={submitting || !junctionId}
            className="rounded-md bg-orange-600 py-1.5 text-sm font-semibold text-white hover:bg-orange-700 disabled:opacity-60"
          >
            {submitting ? 'Reporting...' : 'Report accident'}
          </button>
        </form>
      </Card>

      <Card title={`Active accidents (${activeAccidents.length})`}>
        {activeAccidents.length === 0 ? (
          <EmptyState title="No active accidents" />
        ) : (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {activeAccidents.map((a) => (
              <div key={a.id} className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                <div className="mb-2 flex items-center justify-between">
                  <span className="font-semibold text-slate-700 dark:text-slate-200">{a.junctionId || a.roadId}</span>
                  <Badge variant={SEVERITY_VARIANT[a.severity] || 'neutral'}>{a.severity}</Badge>
                </div>
                <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
                  Detected {fmtTime(a.detectedAt)} via {a.method} - predicted delay {Math.round(a.predictedDelayMin || 0)} min,
                  queue {Math.round(a.predictedQueue || 0)} PCU
                </p>
                <EvidenceImage kind="accidents" filename={a.imageFile} />
                {(a.alternativeRoutes || []).length > 0 && (
                  <div className="mt-2">
                    <CityMap junctions={junctions} accidents={[a]} height="180px" />
                  </div>
                )}
                <button
                  onClick={() => handleResolve(a.id)}
                  disabled={a.status === 'resolving' || resolvingId === a.id}
                  className="mt-3 w-full rounded-md bg-green-600 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-60"
                >
                  {a.status === 'resolving' ? 'Resolving...' : 'Mark resolved'}
                </button>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="Resolved accidents">
        {resolvedAccidents.length === 0 ? (
          <EmptyState title="No resolved accidents yet" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-400">
                <tr>
                  <th className="py-1.5 pr-4">Location</th>
                  <th className="py-1.5 pr-4">Severity</th>
                  <th className="py-1.5 pr-4">Detected</th>
                  <th className="py-1.5">Resolved</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {resolvedAccidents.map((a) => (
                  <tr key={a.id}>
                    <td className="py-1.5 pr-4 font-medium text-slate-700 dark:text-slate-200">{a.junctionId || a.roadId}</td>
                    <td className="py-1.5 pr-4"><Badge variant={SEVERITY_VARIANT[a.severity] || 'neutral'}>{a.severity}</Badge></td>
                    <td className="py-1.5 pr-4 text-slate-500 dark:text-slate-400">{fmtTime(a.detectedAt)}</td>
                    <td className="py-1.5 text-slate-500 dark:text-slate-400">{fmtTime(a.resolvedAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
