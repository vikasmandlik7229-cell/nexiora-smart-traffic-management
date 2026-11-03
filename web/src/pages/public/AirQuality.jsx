import { useMemo, useState } from 'react'
import { limit } from '../../lib/query'
import { CloudFog, Leaf, Radio } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { useCollection } from '../../hooks/useCollection'
import { Card } from '../../components/Card'
import { Badge } from '../../components/Badge'
import { InfoTip } from '../../components/InfoTip'
import { JunctionSelector } from '../../components/JunctionSelector'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonCard } from '../../components/Skeleton'

const AQI_COLORS = {
  1: 'bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-300',
  2: 'bg-lime-100 text-lime-700 dark:bg-lime-500/15 dark:text-lime-300',
  3: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',
  4: 'bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-300',
  5: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300',
}

export default function AirQuality() {
  const { data: junctions, loading } = useCollection('junctions', [limit(10)])
  const { data: readings } = useCollection('air_quality', [limit(10)])
  const { data: logs } = useCollection('air_quality_logs', [limit(200)])
  const [selected, setSelected] = useState(null)

  const junctionId = selected || junctions[0]?.id
  const reading = readings.find((r) => r.id === junctionId)

  const trend = useMemo(() => {
    return logs
      .filter((l) => l.junctionId === junctionId && l.timestamp)
      .sort((a, b) => a.timestamp - b.timestamp)
      .slice(-48)
      .map((l) => ({ time: new Date(l.timestamp * 1000).toLocaleString([], { month: 'numeric', day: 'numeric', hour: '2-digit' }), aqi: l.aqi }))
  }, [logs, junctionId])

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
        <CloudFog size={20} className="text-accent-500" />
        <h1 className="text-xl font-bold text-slate-800 dark:text-white">Air Quality</h1>
        <InfoTip>
          AQI (Air Quality Index) runs 1 (Good) to 5 (Very Poor). At 4 or above, the junction's signal automatically
          switches to Eco mode to reduce idling. Readings are live from OpenWeather when available, or a clearly
          labelled simulated fallback otherwise.
        </InfoTip>
      </div>

      <JunctionSelector junctions={junctions} selected={junctionId} onSelect={setSelected} />

      {!reading ? (
        <EmptyState title="No air quality data yet" hint="Run backend/airquality/aqi.py (or let run_signals.py poll it automatically)." icon={CloudFog} />
      ) : (
        <>
          <Card>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <span className={`rounded-full px-4 py-2 text-lg font-bold ${AQI_COLORS[reading.aqi] || AQI_COLORS[3]}`}>
                  AQI {reading.aqi} - {reading.label}
                </span>
                {reading.aqi >= 4 && (
                  <Badge variant="eco">
                    <Leaf size={12} className="mr-1 inline" /> Eco mode active
                  </Badge>
                )}
              </div>
              <span className="flex items-center gap-1 text-xs text-slate-400">
                <Radio size={12} /> {reading.source === 'live' ? 'Live (OpenWeather)' : 'Simulated'}
              </span>
            </div>
          </Card>

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {[
              ['PM2.5', reading.pm2_5, 'ug/m3', 'Fine particles small enough to enter the lungs - the pollutant most linked to health effects.'],
              ['PM10', reading.pm10, 'ug/m3', 'Coarser dust and particulate matter, e.g. from road surfaces and construction.'],
              ['NO2', reading.no2, 'ug/m3', 'Nitrogen dioxide - mainly from vehicle exhaust, a direct marker of traffic pollution.'],
              ['CO', reading.co, 'ug/m3', 'Carbon monoxide - produced by idling engines, which is exactly what Eco mode reduces.'],
            ].map(([label, value, unit, explain]) => (
              <Card key={label}>
                <p className="flex items-center gap-1 text-xs font-medium uppercase text-slate-500 dark:text-slate-400">
                  {label}
                  <InfoTip>{explain}</InfoTip>
                </p>
                <p className="mt-1 text-xl font-bold text-slate-800 dark:text-white">
                  {value != null ? value.toFixed(1) : '-'} <span className="text-xs font-normal text-slate-400">{unit}</span>
                </p>
              </Card>
            ))}
          </div>

          <Card title="24-hour trend">
            {trend.length === 0 ? (
              <EmptyState title="Not enough history yet" hint="AQI logs accumulate over time as the backend polls." />
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={trend}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-800" />
                  <XAxis dataKey="time" tick={{ fontSize: 10 }} />
                  <YAxis domain={[1, 5]} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Line type="monotone" dataKey="aqi" stroke="#f59e0b" strokeWidth={2} dot={{ r: 2 }} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </Card>
        </>
      )}
    </div>
  )
}
