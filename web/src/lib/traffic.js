// Shared helpers for turning live_counts docs into a congestion level,
// matching the thresholds used across the public pages.
//
// junctionPcu sums each lane's real PCU-weighted load (l.pcu - car=1,
// bike=0.5, bus/truck=3, see backend config.py), NOT raw vehicle count -
// it used to sum l.count instead, so a junction full of bikes and one full
// of trucks/buses read as equally congested, and the "Vehicles now" stat
// card's own tooltip ("a PCU-weighted total, not a raw vehicle count") was
// simply false. congestionLevel's thresholds are junction-wide (summed
// across J1's 4 lanes), not per-lane - compare with densityBarColor below,
// which uses per-lane thresholds against a single lane's own PCU.
export function junctionPcu(counts) {
  if (!counts?.lanes) return 0
  return Math.round(Object.values(counts.lanes).reduce((sum, l) => sum + (l.pcu || 0), 0) * 10) / 10
}

// Thresholds are a judgment call, not derived from a formula: backend
// config.py's LANE_CAPACITY_PCU=20 is "one lane at capacity", and typical
// demo traffic on this footage sums to roughly 15-40 PCU across all 4
// lanes - so low/medium/high are set to spread that real range instead of
// the old 5/12 thresholds (sized for one lane's PCU, not a 4-lane total),
// which made nearly every junction read "high" almost all the time.
export function congestionLevel(pcu) {
  if (pcu < 15) return 'low'
  if (pcu < 30) return 'medium'
  return 'high'
}

export const CONGESTION_COLORS = {
  low: '#43A047',
  medium: '#FFB300',
  high: '#E53935',
}

// J1's real approach bearings, seeded in db/seed.py: lane1=North(0),
// lane2=East(90), lane3=South(180), lane4=West(270) - a standard compass
// mapping, not decorative.
const BEARING_LABELS = { 0: 'North', 90: 'East', 180: 'South', 270: 'West' }
export function laneDirection(approaches, laneId) {
  const bearing = approaches?.[laneId]
  return bearing != null ? BEARING_LABELS[bearing] ?? `${bearing}°` : null
}

export function densityBarColor(pcu) {
  if (pcu < 5) return 'bg-signal-green'
  if (pcu < 12) return 'bg-signal-amber'
  return 'bg-signal-red'
}

// Local calendar date (YYYY-MM-DD), not UTC - toISOString().slice(0,10) rolls
// over at UTC midnight, which is 5:30am IST, so a UTC-based "today" filter
// shows the wrong day's data for the first/last few hours of the local day.
export function localDateStr(date = new Date()) {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}
