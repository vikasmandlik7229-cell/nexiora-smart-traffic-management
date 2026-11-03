import { useEffect, useMemo } from 'react'
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet'
import L from 'leaflet'
import { junctionPcu, congestionLevel, CONGESTION_COLORS } from '../lib/traffic'

const ROAD_COLORS = { open: '#94a3b8', congested: '#FFB300', blocked: '#E53935' }

function divIcon(html, size = 26) {
  return L.divIcon({ html, className: '', iconSize: [size, size], iconAnchor: [size / 2, size / 2] })
}

function junctionIcon(level, isSelected) {
  const color = CONGESTION_COLORS[level] || CONGESTION_COLORS.low
  const ring = isSelected ? '0 0 0 4px rgba(59,130,246,0.4)' : 'none'
  return divIcon(
    `<div style="width:20px;height:20px;border-radius:9999px;background:${color};border:2px solid white;box-shadow:${ring}"></div>`,
  )
}

const ambulanceIcon = divIcon(
  '<div style="font-size:22px;line-height:1;filter:drop-shadow(0 1px 2px rgba(0,0,0,0.5))">\u{1F691}</div>',
  26,
)
const accidentIcon = divIcon(
  '<div style="font-size:20px;line-height:1;filter:drop-shadow(0 1px 2px rgba(0,0,0,0.5))">⚠️</div>',
  22,
)

function FitBounds({ points }) {
  const map = useMap()
  useEffect(() => {
    if (points.length === 0) return
    if (points.length === 1) {
      map.setView(points[0], 14)
      return
    }
    map.fitBounds(L.latLngBounds(points), { padding: [40, 40] })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(points)])
  return null
}

/** Reusable Leaflet city map: junctions coloured by congestion, roads
 * coloured by status, a live ambulance + route, and accident markers with
 * detour polylines. Pure presentational - callers pass live polled data. */
export function CityMap({
  junctions = [],
  signals = [],
  liveCounts = [],
  roads = [],
  accidents = [],
  ambulance = null,
  selectedJunctionId = null,
  onSelectJunction = () => {},
  height = '420px',
}) {
  const junctionById = useMemo(() => Object.fromEntries(junctions.map((j) => [j.id, j])), [junctions])
  const signalById = useMemo(() => Object.fromEntries(signals.map((s) => [s.id, s])), [signals])
  const countsById = useMemo(() => Object.fromEntries(liveCounts.map((c) => [c.id, c])), [liveCounts])
  const activeAccidents = useMemo(() => accidents.filter((a) => a.status === 'active'), [accidents])

  const fitPoints = useMemo(() => junctions.map((j) => [j.lat, j.lng]).filter((p) => p[0] != null), [junctions])
  const center = fitPoints[0] || [19.076, 72.8777]

  return (
    <div style={{ height }} className="overflow-hidden rounded-lg">
      <MapContainer center={center} zoom={13} style={{ height: '100%', width: '100%' }} scrollWheelZoom={false}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitBounds points={fitPoints} />

        {roads.map((r) => {
          const from = junctionById[r.from]
          const to = junctionById[r.to]
          if (!from || !to) return null
          const color = ROAD_COLORS[r.status] || ROAD_COLORS.open
          return (
            <Polyline
              key={r.id || `${r.from}_${r.to}`}
              positions={[[from.lat, from.lng], [to.lat, to.lng]]}
              pathOptions={{ color, weight: r.status === 'blocked' ? 4 : 3, dashArray: r.status === 'blocked' ? '6 6' : null, opacity: 0.8 }}
            />
          )
        })}

        {activeAccidents.flatMap((a) =>
          (a.alternativeRoutes || []).map((route, i) => (
            <Polyline
              key={`detour-${a.id}-${i}`}
              positions={(route.polyline || []).map((p) => [p.lat, p.lng])}
              pathOptions={{ color: '#43A047', weight: 4, dashArray: '8 6', opacity: 0.9 }}
            />
          )),
        )}

        {ambulance?.active && ambulance.routePolyline?.length > 0 && (
          <Polyline
            positions={ambulance.routePolyline.map((p) => [p.lat, p.lng])}
            pathOptions={{ color: '#2563eb', weight: 4, dashArray: '2 8', opacity: 0.9 }}
          />
        )}

        {junctions.map((j) => {
          const signal = signalById[j.id]
          const pcu = junctionPcu(countsById[j.id])
          const level = congestionLevel(pcu)
          return (
            <Marker
              key={j.id}
              position={[j.lat, j.lng]}
              icon={junctionIcon(level, j.id === selectedJunctionId)}
              eventHandlers={{ click: () => onSelectJunction(j.id) }}
            >
              <Popup>
                <div className="text-sm">
                  <p className="font-semibold">{j.id} - {j.name}</p>
                  <p>Mode: {signal?.mode || 'unknown'}</p>
                  <p>Load: {pcu} PCU ({level})</p>
                  {j.isVirtual && <p className="italic text-slate-500">Virtual junction</p>}
                </div>
              </Popup>
            </Marker>
          )
        })}

        {activeAccidents.map((a) => {
          const fallback = junctionById[a.junctionId]
          const lat = a.lat ?? fallback?.lat
          const lng = a.lng ?? fallback?.lng
          if (lat == null || lng == null) return null
          return (
            <Marker key={a.id} position={[lat, lng]} icon={accidentIcon}>
              <Popup>
                <div className="text-sm">
                  <p className="font-semibold">Accident - {a.severity}</p>
                  <p>{a.junctionId || a.roadId}</p>
                  <p>Predicted delay: {Math.round(a.predictedDelayMin || 0)} min</p>
                </div>
              </Popup>
            </Marker>
          )
        })}

        {ambulance?.active && ambulance.lat != null && ambulance.lng != null && (
          <Marker position={[ambulance.lat, ambulance.lng]} icon={ambulanceIcon}>
            <Popup>
              <div className="text-sm">
                <p className="font-semibold">{ambulance.vehicleId}</p>
                <p>Next junction: {ambulance.nextJunctionId || '-'}</p>
                <p>ETA: {ambulance.etaNextS != null ? `${Math.round(ambulance.etaNextS)}s` : '-'}</p>
              </div>
            </Popup>
          </Marker>
        )}
      </MapContainer>
    </div>
  )
}

export function CityMapLegend() {
  const rows = [
    ['Low congestion', CONGESTION_COLORS.low],
    ['Medium congestion', CONGESTION_COLORS.medium],
    ['High congestion', CONGESTION_COLORS.high],
    ['Blocked road', ROAD_COLORS.blocked],
    ['Detour', '#43A047'],
  ]
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
      {rows.map(([label, color]) => (
        <span key={label} className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
          {label}
        </span>
      ))}
      <span className="flex items-center gap-1.5">{'\u{1F691}'} Ambulance</span>
      <span className="flex items-center gap-1.5">{'⚠️'} Accident</span>
    </div>
  )
}
