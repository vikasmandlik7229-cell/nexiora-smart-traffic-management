// Marks alerts as read (backend/api/server.py's POST /api/alerts/mark-read),
// called when the dashboard's notification bell dropdown is opened.
import { apiFetch } from '../api'

export async function markAlertsRead(ids) {
  if (!ids.length) return
  await apiFetch('/api/alerts/mark-read', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  })
}
