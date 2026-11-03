// Emergency request + trip-control writes. requestedBy is set server-side
// from the auth token (driver or controller), not sent by the client.
import { apiFetch } from '../api'

export async function submitEmergencyRequest({ vehicleId, tagId, destinationJunction, source = 'web' }) {
  const res = await apiFetch('/api/emergency-requests', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ vehicleId, tagId, destinationJunction, source }),
  })
  const { id } = await res.json()
  return id
}

// Writes trip_control/{vehicleId} - the website can't write emergency/active
// directly, so emergency/ambulance_sim.py polls this doc every ~1s while a
// trip is running and ends the trip early when it sees endRequested=true.
export async function requestEndTrip(vehicleId) {
  await apiFetch(`/api/trip-control/${vehicleId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ endRequested: true }),
  })
}
