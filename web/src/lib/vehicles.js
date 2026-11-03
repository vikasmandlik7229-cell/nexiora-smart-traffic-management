// authorised_vehicles writes - vehicleId is the document id (chosen by the
// controller), matching backend/db/seed.py's seeding convention.
import { apiFetch } from '../api'

export async function saveAuthorisedVehicle(vehicleId, data) {
  await apiFetch(`/api/authorised-vehicles/${vehicleId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function setVehicleActive(vehicleId, active) {
  return saveAuthorisedVehicle(vehicleId, { active })
}
