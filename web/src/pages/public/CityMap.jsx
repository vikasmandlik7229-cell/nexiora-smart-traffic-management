import { useMemo, useState } from 'react'
import { limit } from '../../lib/query'
import { Map as MapIcon } from 'lucide-react'
import { useCollection } from '../../hooks/useCollection'
import { useDoc } from '../../hooks/useDoc'
import { Card } from '../../components/Card'
import { CityMap as CityMapView, CityMapLegend } from '../../components/CityMap'
import { TrafficLight } from '../../components/TrafficLight'
import { CongestionChip } from '../../components/CongestionChip'
import { ModeBadge } from '../../components/Badge'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonCard } from '../../components/Skeleton'
import { InfoTip } from '../../components/InfoTip'
import { junctionPcu, congestionLevel } from '../../lib/traffic'

export default function CityMap() {
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
        <InfoTip>
          Click any coloured dot to see that junction's live signals. Dot colour shows congestion (green/amber/red),
          road colour shows status, and ambulance/accident icons appear automatically when active - see the legend
          below the map.
        </InfoTip>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CityMapView
            junctions={junctions}
            signals={signals}
            liveCounts={liveCounts}
            roads={roads}
            accidents={accidents}
            ambulance={ambulance}
            selectedJunctionId={selectedJunction?.id}
            onSelectJunction={setSelected}
            height="480px"
          />
          <div className="mt-3">
            <CityMapLegend />
          </div>
        </Card>

        <Card title={selectedJunction ? `${selectedJunction.id} - ${selectedJunction.name}` : 'Select a junction'}>
          {!selectedJunction ? (
            <EmptyState title="Click a junction on the map" />
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                {selectedSignal && <ModeBadge mode={selectedSignal.mode} />}
                <span className="flex items-center gap-1">
                  <CongestionChip level={congestionLevel(selectedPcu)} />
                  <InfoTip>Based on total PCU-weighted traffic load currently at this junction.</InfoTip>
                </span>
              </div>
              {selectedSignal?.lanes ? (
                <div className="grid grid-cols-2 gap-3">
                  {Object.entries(selectedSignal.lanes).map(([laneId, laneData]) => (
                    <div key={laneId} className="flex flex-col items-center gap-1 rounded-lg border border-slate-200 p-2 dark:border-slate-800">
                      <span className="text-xs font-medium text-slate-600 dark:text-slate-300">{laneId}</span>
                      <TrafficLight
                        state={laneData.state}
                        phaseEndsAt={laneId === selectedSignal.activeLane ? selectedSignal.phaseEndsAt : null}
                        size="sm"
                      />
                      <span className="text-xs text-slate-400">{Math.round(laneData.load ?? laneData.count ?? 0)} PCU</span>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState title="No live signal for this junction" hint="Virtual junctions use simulated counts." />
              )}
              {selectedJunction.isVirtual && (
                <p className="text-xs italic text-slate-400">This is a virtual junction (no real camera feed).</p>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
