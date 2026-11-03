import { useMemo, useState } from 'react'
import { limit } from '../../lib/query'
import { Map as MapIcon, Ambulance, AlertTriangle } from 'lucide-react'
import { useCollection } from '../../hooks/useCollection'
import { useDoc } from '../../hooks/useDoc'
import { Card } from '../../components/Card'
import { CityMap, CityMapLegend } from '../../components/CityMap'
import { TrafficLight } from '../../components/TrafficLight'
import { CongestionChip } from '../../components/CongestionChip'
import { ModeBadge } from '../../components/Badge'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonCard } from '../../components/Skeleton'
import { junctionPcu, congestionLevel } from '../../lib/traffic'

export default function CityMapDashboard() {
  const { data: junctions, loading } = useCollection('junctions', [limit(10)])
  const { data: signals } = useCollection('signals', [limit(10)])
  const { data: liveCounts } = useCollection('live_counts', [limit(10)])
  const { data: roads } = useCollection('roads', [limit(40)])
  const { data: accidents } = useCollection('accidents', [limit(20)])
  const { data: ambulance } = useDoc('emergency', 'active')
  const [selected, setSelected] = useState(null)

  const countsById = useMemo(() => Object.fromEntries(liveCounts.map((c) => [c.id, c])), [liveCounts])
  const signalById = useMemo(() => Object.fromEntries(signals.map((s) => [s.id, s])), [signals])
  const selectedJunction = junctions.find((j) => j.id === selected) || junctions[0]
  const selectedSignal = selectedJunction && signalById[selectedJunction.id]
  const selectedPcu = selectedJunction ? junctionPcu(countsById[selectedJunction.id]) : 0
  const activeAccidents = accidents.filter((a) => a.status === 'active')
  const blockedRoads = roads.filter((r) => r.status === 'blocked')

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    )
  }

  if (junctions.length === 0) {
    return <EmptyState title="No junctions yet" hint="Run backend/db/seed.py to seed junction data." icon={MapIcon} />
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <MapIcon size={20} className="text-accent-500" />
        <h1 className="text-xl font-bold text-slate-800 dark:text-white">City Map</h1>
      </div>

      {ambulance?.active && (
        <div className="flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white">
          <Ambulance size={18} className="animate-pulse" />
          {ambulance.vehicleId} en route, next junction {ambulance.nextJunctionId || '-'}, ETA{' '}
          {ambulance.etaNextS != null ? `${Math.round(ambulance.etaNextS)}s` : '-'} - pre-empted:{' '}
          {(ambulance.preempted || []).join(', ') || 'none yet'}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CityMap
            junctions={junctions}
            signals={signals}
            liveCounts={liveCounts}
            roads={roads}
            accidents={accidents}
            ambulance={ambulance}
            selectedJunctionId={selectedJunction?.id}
            onSelectJunction={setSelected}
            height="520px"
          />
          <div className="mt-3">
            <CityMapLegend />
          </div>
        </Card>

        <div className="space-y-4">
          <Card title={selectedJunction ? `${selectedJunction.id} - ${selectedJunction.name}` : 'Select a junction'}>
            {!selectedJunction ? (
              <EmptyState title="Click a junction on the map" />
            ) : (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  {selectedSignal && <ModeBadge mode={selectedSignal.mode} />}
                  <CongestionChip level={congestionLevel(selectedPcu)} />
                </div>
                {selectedSignal?.lanes ? (
                  <div className="grid grid-cols-2 gap-3">
                    {Object.entries(selectedSignal.lanes).map(([laneId, laneData]) => (
                      <div key={laneId} className="flex flex-col items-center gap-1 rounded-lg border border-slate-200 p-2 dark:border-slate-800">
                        <span className="text-xs font-medium text-slate-600 dark:text-slate-300">{laneId}</span>
                        <TrafficLight state={laneData.state} size="sm" />
                        <span className="text-xs text-slate-400">{Math.round(laneData.load ?? laneData.count ?? 0)} PCU</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState title="No live signal for this junction" hint="Virtual junctions use simulated counts." />
                )}
              </div>
            )}
          </Card>

          <Card title="Active accidents">
            {activeAccidents.length === 0 ? (
              <p className="text-sm text-slate-400">No active accidents.</p>
            ) : (
              <ul className="space-y-2">
                {activeAccidents.map((a) => (
                  <li key={a.id} className="flex items-start gap-2 text-sm">
                    <AlertTriangle size={14} className="mt-0.5 shrink-0 text-orange-500" />
                    <span className="text-slate-600 dark:text-slate-300">
                      {a.junctionId || a.roadId} - {a.severity} - {Math.round(a.predictedDelayMin || 0)} min delay
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Blocked roads">
            {blockedRoads.length === 0 ? (
              <p className="text-sm text-slate-400">All roads open.</p>
            ) : (
              <ul className="space-y-1 text-sm text-slate-600 dark:text-slate-300">
                {blockedRoads.map((r) => (
                  <li key={r.id}>{r.from} &rarr; {r.to}</li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}
