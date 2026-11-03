import { useMemo, useState } from 'react'
import { limit } from '../../lib/query'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { TrendingUp } from 'lucide-react'
import { useCollection } from '../../hooks/useCollection'
import { Card } from '../../components/Card'
import { CongestionChip } from '../../components/CongestionChip'
import { InfoTip } from '../../components/InfoTip'
import { JunctionSelector } from '../../components/JunctionSelector'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonCard } from '../../components/Skeleton'

export default function Predictions() {
  const { data: junctions, loading } = useCollection('junctions', [limit(10)])
  const { data: predictions } = useCollection('predictions', [limit(10)])
  const { data: shortPredictions } = useCollection('short_predictions', [limit(10)])
  const [selected, setSelected] = useState(null)

  const junctionId = selected || junctions[0]?.id
  const peakData = predictions.find((p) => p.id === junctionId)
  const shortData = shortPredictions.find((p) => p.id === junctionId)

  const chartData = useMemo(() => {
    if (!peakData?.hourly) return []
    return peakData.hourly.map((row) => ({
      time: new Date(row.timestamp).toLocaleTimeString([], { hour: '2-digit' }),
      predicted: Math.round(row.predictedCount),
      isPeak: row.isPeak,
    }))
  }, [peakData])

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
      <div className="flex items-center gap-2">
        <TrendingUp size={20} className="text-accent-500" />
        <h1 className="text-xl font-bold text-slate-800 dark:text-white">Predictions</h1>
        <InfoTip>
          Two separate machine-learning models: one predicts the next 5-10 minutes from a rolling window of recent
          counts, the other predicts peak hours over the next 24 hours from historical patterns.
        </InfoTip>
      </div>

      <JunctionSelector junctions={junctions} selected={junctionId} onSelect={setSelected} />

      <Card
        title="Next 5 / 10 minutes per lane"
        action={
          <InfoTip>
            Low/Medium/High compares the +5 minute prediction against this lane's typical capacity - the same scale
            used everywhere else in the app.
          </InfoTip>
        }
      >
        {!shortData?.lanes ? (
          <EmptyState title="No short-term predictions yet" hint="Run backend/prediction/predict_short.py (only covers J1's real lanes)." />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {Object.entries(shortData.lanes).map(([lane, p]) => (
              <div key={lane} className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                <p className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">{lane}</p>
                {p.status ? (
                  <p className="text-xs text-slate-400">{p.status}</p>
                ) : (
                  <div className="flex items-center justify-between text-sm">
                    <div className="text-center">
                      <p className="text-xs text-slate-400">now</p>
                      <p className="font-bold text-slate-800 dark:text-white">{Math.round(p.now)}</p>
                    </div>
                    <span className="text-slate-300 dark:text-slate-600">&rarr;</span>
                    <div className="text-center">
                      <p className="text-xs text-slate-400">+5m</p>
                      <p className="font-bold text-slate-800 dark:text-white">{Math.round(p.in5)}</p>
                    </div>
                    <span className="text-slate-300 dark:text-slate-600">&rarr;</span>
                    <div className="text-center">
                      <p className="text-xs text-slate-400">+10m</p>
                      <p className="font-bold text-slate-800 dark:text-white">{Math.round(p.in10)}</p>
                    </div>
                  </div>
                )}
                {p.level && (
                  <div className="mt-2">
                    <CongestionChip level={p.level} />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card
        title="Next 24 hours"
        action={
          <InfoTip>
            Trained on historical hourly traffic patterns. The top 20% busiest predicted hours are marked as peak
            hours (shaded below) - the controller gives those lanes a head start on green time just before they
            arrive.
          </InfoTip>
        }
      >
        {chartData.length === 0 ? (
          <EmptyState title="No peak-hour predictions yet" hint="Run backend/prediction/predict_peak.py (after train_peak.py)." />
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-800" />
              <XAxis dataKey="time" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              {chartData.map((row, i) =>
                row.isPeak ? (
                  <ReferenceLine key={i} x={row.time} stroke="#f59e0b" strokeOpacity={0.15} strokeWidth={14} />
                ) : null,
              )}
              <Area type="monotone" dataKey="predicted" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.15} />
              <Line type="monotone" dataKey="predicted" stroke="#3b82f6" strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        )}
        <p className="mt-2 text-xs text-slate-400">Shaded columns mark predicted peak hours (top 20%).</p>
      </Card>
    </div>
  )
}
