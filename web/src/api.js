// Helpers for the local FastAPI backend (backend/api/server.py).
import { getToken } from './lib/auth'
import { API_URL, constraintsToParams } from './lib/query'

export { API_URL }

export async function getIdToken() {
  return getToken()
}

export async function apiFetch(path, options = {}) {
  const token = await getIdToken()
  const headers = { ...(options.headers || {}) }
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(`${API_URL}${path}`, { ...options, headers })
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`)
  return res
}

export async function fetchCollection(name, constraints = []) {
  const params = constraintsToParams(constraints)
  const res = await apiFetch(`/api/collection/${name}?${params.toString()}`)
  const data = await res.json()
  return data.docs
}

export async function fetchDoc(name, id) {
  const token = await getIdToken()
  const headers = token ? { Authorization: `Bearer ${token}` } : {}
  const res = await fetch(`${API_URL}/api/doc/${name}/${id}`, { headers })
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`API /api/doc/${name}/${id} failed: ${res.status}`)
  return res.json()
}

export async function checkHealth() {
  const res = await fetch(`${API_URL}/api/health`)
  if (!res.ok) throw new Error('backend unhealthy')
  return res.json()
}

export async function fetchReports() {
  const res = await apiFetch('/api/reports')
  return res.json()
}

// For <img>/MJPEG src attributes, which can't send an Authorization header -
// the backend accepts the token as a query param for exactly this reason.
export async function streamUrl(lane) {
  const token = await getIdToken()
  const params = new URLSearchParams()
  if (lane) params.set('lane', lane)
  if (token) params.set('token', token)
  const qs = params.toString()
  return `${API_URL}/api/stream/j1${qs ? `?${qs}` : ''}`
}

export async function evidenceUrl(kind, filename) {
  const token = await getIdToken()
  const params = new URLSearchParams()
  if (token) params.set('token', token)
  return `${API_URL}/api/evidence/${kind}/${filename}?${params.toString()}`
}

export async function reportUrl(filename) {
  const token = await getIdToken()
  const params = new URLSearchParams()
  if (token) params.set('token', token)
  return `${API_URL}/api/reports/${filename}?${params.toString()}`
}
