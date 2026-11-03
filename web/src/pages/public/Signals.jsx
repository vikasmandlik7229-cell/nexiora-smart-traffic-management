import { useState } from 'react'
import { limit } from '../../lib/query'
import { HelpCircle, X } from 'lucide-react'
import { useCollection } from '../../hooks/useCollection'
import { Card } from '../../components/Card'
import { TrafficLight } from '../../components/TrafficLight'
import { ModeBadge } from '../../components/Badge'
import { InfoTip } from '../../components/InfoTip'
import { JunctionSelector } from '../../components/JunctionSelector'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonCard } from '../../components/Skeleton'

function HowItWorksModal({ onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="max-w-md rounded-xl bg-white p-6 dark:bg-slate-900"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-bold text-slate-800 dark:text-white">How adaptive signals work</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
            <X size={20} />
          </button>
        </div>
        <ul className="list-disc space-y-2 pl-5 text-sm text-slate-600 dark:text-slate-300">
          <li>Each lane's green time scales with how many vehicles (weighted by size - a bus counts more than a bike) are waiting.</li>
          <li>A lane that's waited too long always gets served next, so no lane is ever starved indefinitely.</li>
          <li>Green always passes through yellow before turning red - even for ambulance pre-emption or a manual override.</li>
          <li>An approaching authorised ambulance can force a lane green early, clearing the queue before it arrives.</li>
          <li>During high-pollution periods, "eco mode" shortens cycles to reduce idling.</li>
        </ul>
      </div>
    </div>
  )
}

export default function Signals() {
  const { data: junctions, loading } = useCollection('junctions', [limit(10)])
  const { data: signals } = useCollection('signals', [limit(10)])
  const [selected, setSelected] = useState(null)
  const [showHelp, setShowHelp] = useState(false)

  const junctionId = selected || junctions[0]?.id
  const signal = signals.find((s) => s.id === junctionId)
  const lanes = signal?.lanes || {}

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    )
  }

  if (junctions.length === 0) {
    return <EmptyState title="No junctions yet" hint="Run backend/db/seed.py to seed junction data." />
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <JunctionSelector junctions={junctions} selected={junctionId} onSelect={setSelected} />
        <button
          onClick={() => setShowHelp(true)}
          className="flex items-center gap-1 text-sm text-accent-600 hover:underline dark:text-accent-400"
        >
          <HelpCircle size={16} /> How it works
        </button>
      </div>

      {!signal ? (
        <EmptyState title={`No live signal data for ${junctionId}`} hint="Run backend/run_signals.py (for J1) or backend/signals/virtual_junctions.py (for others)." />
      ) : (
        <>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold text-slate-800 dark:text-white">{junctionId}</h1>
            <ModeBadge mode={signal.mode} />
            <InfoTip>
              Adaptive (timing follows real traffic), Eco (shorter cycles when air quality is poor), Emergency (an
              ambulance has priority), Accident (a lane is blocked), Peak (anticipating a predicted busy spell), or
              Manual (a controller has taken over).
            </InfoTip>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {Object.entries(lanes).map(([laneId, laneData]) => (
              <Card key={laneId} className="flex flex-col items-center gap-3 transition-shadow hover:shadow-md">
                <span className="font-semibold text-slate-700 dark:text-slate-200">{laneId}</span>
                <TrafficLight
                  state={laneData.state}
                  phaseEndsAt={laneId === signal.activeLane ? signal.phaseEndsAt : null}
                  size="lg"
                />
                <div className="flex items-center gap-1 text-center text-sm text-slate-500 dark:text-slate-400">
                  <p>Load: {Math.round(laneData.load ?? laneData.count ?? 0)} PCU</p>
                  <InfoTip>
                    PCU (Passenger Car Unit) weights vehicles by road space: car = 1, bike = 0.5, bus/truck = 3. A
                    higher load earns this lane a longer green phase.
                  </InfoTip>
                </div>
              </Card>
            ))}
          </div>
        </>
      )}

      {showHelp && <HowItWorksModal onClose={() => setShowHelp(false)} />}
    </div>
  )
}
