import { useMemo } from 'react'
import { limit } from '../../lib/query'
import { BarChart3, Fuel, Leaf, TrendingDown } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, Legend, Line, ComposedChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useCollection } from '../../hooks/useCollection'
import { Card } from '../../components/Card'
import { StatCard } from '../../components/StatCard'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonCard } from '../../components/Skeleton'

// metrics/{junctionId}_{date} - date is always the trailing YYYY-MM-DD.
function dateFromId(id) {
  return id.slice(-10)
}

export default function Performance() {
  const { data: metrics, loading } = useCollection('metrics', [limit(200)])

  const byDate = useMemo(() => {
    const groups = {}
    metrics.forEach((m) => {
      const date = dateFromId(m.id)
      if (!groups[date]) groups[date] = { date, adaptive: [], fixed: [], fuel: 0, co2: 0 }
      groups[date].adaptive.push(m.avgWaitAdaptiveS || 0)
      groups[date].fixed.push(m.avgWaitFixedS || 0)
      groups[date].fuel += m.fuelSavedL || 0
      groups[date].co2 += m.co2SavedKg || 0
    })
    return Object.values(groups)
      .map((g) => ({
        date: g.date,
        adaptive: g.adaptive.reduce((a, b) => a + b, 0) / g.adaptive.length,
        fixed: g.fixed.reduce((a, b) => a + b, 0) / g.fixed.length,
        fuel: g.fuel,
        co2: g.co2,
      }))
      .sort((a, b) => a.date.localeCompare(b.date))
      .slice(-7)
  }, [metrics])

  const totals = useMemo(() => {
    if (byDate.length === 0) return null
    const avgAdaptive = byDate.reduce((s, d) => s + d.adaptive, 0) / byDate.length
    const avgFixed = byDate.reduce((s, d) => s + d.fixed, 0) / byDate.length
    const totalFuel = byDate.reduce((s, d) => s + d.fuel, 0)
    const totalCo2 = byDate.reduce((s, d) => s + d.co2, 0)
    const reductionPct = avgFixed > 0 ? ((avgFixed - avgAdaptive) / avgFixed) * 100 : 0
    return { avgAdaptive, avgFixed, totalFuel, totalCo2, reductionPct }
  }, [byDate])

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}
      </div>
    )
  }

  if (byDate.length === 0) {
    return (
      <EmptyState
        title="No performance data yet"
        hint="Metrics publish every 5 minutes while backend/run_signals.py is running (metrics/publish.py)."
        icon={BarChart3}
      />
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <BarChart3 size={20} className="text-accent-500" />
        <h1 className="text-xl font-bold text-slate-800 dark:text-white">Performance (last 7 days)</h1>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Avg wait, adaptive" value={`${totals.avgAdaptive.toFixed(1)}s`} icon={TrendingDown} accent="green" />
        <StatCard label="Avg wait, fixed-time" value={`${totals.avgFixed.toFixed(1)}s`} icon={TrendingDown} accent="slate" />
        <StatCard label="Wait reduction" value={`${totals.reductionPct.toFixed(0)}%`} icon={TrendingDown} accent="green" hint="adaptive vs fixed" />
        <StatCard label="Fuel saved" value={`${totals.totalFuel.toFixed(1)} L`} icon={Fuel} accent="amber" hint={`${totals.totalCo2.toFixed(1)} kg CO2`} />
      </div>

      <Card title="Average wait: adaptive vs fixed-time">
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={byDate}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-800" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} unit="s" />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="adaptive" name="Adaptive" stroke="#43A047" strokeWidth={2} />
            <Line type="monotone" dataKey="fixed" name="Fixed-time" stroke="#94a3b8" strokeWidth={2} />
          </ComposedChart>
        </ResponsiveContainer>
      </Card>

      <Card title="Fuel and CO2 saved per day">
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={byDate}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-800" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Legend />
            <Bar dataKey="fuel" name="Fuel saved (L)" fill="#FFB300" radius={[4, 4, 0, 0]} />
            <Bar dataKey="co2" name="CO2 saved (kg)" fill="#43A047" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
        <p className="mt-2 flex items-center gap-1 text-xs text-slate-400">
          <Leaf size={12} /> Idle-fuel assumptions are configurable in config.py (IDLE_FUEL_L_PER_HOUR, CO2_KG_PER_L) -
          see CLAUDE.md's honesty notes.
        </p>
      </Card>
    </div>
  )
}
