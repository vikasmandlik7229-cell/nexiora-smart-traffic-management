// The website can't write the `accidents` collection directly (enforced by
// the backend's role checks, api/server.py) - reporting creates a pending
// doc in `accident_reports` that backend/accidents/manager.py's report
// listener turns into a full accident record. Resolving flips
// `accidents/{id}.status` to "resolving", which the same module's resolve
// listener picks up and finishes.
import { apiFetch } from '../api'

export async function reportAccident({ junctionId, roadId, laneId, severity, arrivalRatePcuPerMin }) {
  const res = await apiFetch('/api/accident-reports', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      junctionId: junctionId || null,
      roadId: roadId || null,
      laneId: laneId || null,
      severity,
      arrivalRatePcuPerMin: arrivalRatePcuPerMin ?? 6.0,
    }),
  })
  const { id } = await res.json()
  return id
}

export async function markAccidentResolving(accidentId) {
  await apiFetch(`/api/accidents/${accidentId}/resolve`, { method: 'PATCH' })
}
