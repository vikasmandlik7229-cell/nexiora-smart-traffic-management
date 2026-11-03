// Submits a manual-override command for backend/signals/commands.py to pick
// up (polled every 2s). Only force_green/release exist on the backend -
// durationS is clamped server-side to config.MAX_OVERRIDE_SECONDS.
// requestedBy is set server-side from the auth token, not sent here.
import { apiFetch } from '../api'

export const MAX_OVERRIDE_SECONDS = 60 // mirrors backend config.py

export async function submitCommand(junctionId, type, extra = {}) {
  const res = await apiFetch('/api/commands', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ junctionId, type, ...extra }),
  })
  const { id } = await res.json()
  return id
}
