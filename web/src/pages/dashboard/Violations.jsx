import { Fragment, useMemo, useState } from 'react'
import { limit, orderBy } from '../../lib/query'
import { ShieldAlert } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useCollection } from '../../hooks/useCollection'
import { Card } from '../../components/Card'
import { EvidenceImage } from '../../components/EvidenceImage'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonCard } from '../../components/Skeleton'

function fmtTime(sec) {
  if (!sec) return '-'
  return new Date(sec * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function Violations() {
  const { data: violations, loading } = useCollection('violations', [orderBy('timestamp', 'desc'), limit(200)])
  const [laneFilter, setLaneFilter] = useState('all')
  const [typeFilter, setTypeFilter] = useState('all')
  const [expanded, setExpanded] = useState(null)

  const lanes = useMemo(() => [...new Set(violations.map((v) => v.laneId))].sort(), [violations])
  const types = useMemo(() => [...new Set(violations.map((v) => v.vehicleType))].sort(), [violations])

  const filtered = violations.filter(
    (v) => (laneFilter === 'all' || v.laneId === laneFilter) && (typeFilter === 'all' || v.vehicleType === typeFilter),
  )

  const byLane = useMemo(() => {
    const counts = {}
    filtered.forEach((v) => { counts[v.laneId] = (counts[v.laneId] || 0) + 1 })
    return Object.entries(counts).map(([lane, count]) => ({ lane, count }))
  }, [filtered])

  const byHour = useMemo(() => {
    const counts = Array.from({ length: 24 }, (_, h) => ({ hour: `${h}:00`, count: 0 }))
    filtered.forEach((v) => {
      if (v.timestamp) counts[new Date(v.timestamp * 1000).getHours()].count += 1
    })
    return counts
  }, [filtered])

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
        <ShieldAlert size={20} className="text-accent-500" />
        <h1 className="text-xl font-bold text-slate-800 dark:text-white">Violations</h1>
      </div>

      {violations.length === 0 ? (
        <EmptyState
          title="No violations recorded yet"
          hint="Enable config.VIOLATION_TEST_MODE for a demo, or wait for a real red-light crossing while backend/run_signals.py is running."
        />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card title="By lane">
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={byLane}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-800" />
                  <XAxis dataKey="lane" tick={{ fontSize: 12 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#ef4444" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>
            <Card title="By hour of day">
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={byHour}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-800" />
                  <XAxis dataKey="hour" tick={{ fontSize: 9 }} interval={2} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </div>

          <Card title={`Records (${filtered.length})`}>
            <div className="mb-3 flex flex-wrap gap-3">
              <select value={laneFilter} onChange={(e) => setLaneFilter(e.target.value)} className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-white">
                <option value="all">All lanes</option>
                {lanes.map((l) => <option key={l} value={l}>{l}</option>)}
              </select>
              <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-white">
                <option value="all">All vehicle types</option>
                {types.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-slate-400">
                  <tr>
                    <th className="py-1.5 pr-4">Time</th>
                    <th className="py-1.5 pr-4">Lane</th>
                    <th className="py-1.5 pr-4">Vehicle</th>
                    <th className="py-1.5 pr-4">Track #</th>
                    <th className="py-1.5">Evidence</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {filtered.map((v) => (
                    <Fragment key={v.id}>
                      <tr className="cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50" onClick={() => setExpanded(expanded === v.id ? null : v.id)}>
                        <td className="py-1.5 pr-4 text-slate-500 dark:text-slate-400">{fmtTime(v.timestamp)}</td>
                        <td className="py-1.5 pr-4 font-medium text-slate-700 dark:text-slate-200">{v.laneId}</td>
                        <td className="py-1.5 pr-4">{v.vehicleType}</td>
                        <td className="py-1.5 pr-4">#{v.trackId}</td>
                        <td className="py-1.5 text-accent-600 dark:text-accent-400">{expanded === v.id ? 'Hide' : 'View'}</td>
                      </tr>
                      {expanded === v.id && (
                        <tr>
                          <td colSpan={5} className="pb-3">
                            <div className="grid grid-cols-2 gap-3 sm:w-[30rem] sm:grid-cols-3">
                              <EvidenceImage kind="violations" filename={v.imageFile} />
                              <EvidenceImage kind="violations" filename={v.cropFile} />
                              <EvidenceImage kind="violations" filename={v.plateFile} />
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  )
}
