// Local authentication against the backend's own /api/auth endpoints,
// replacing Firebase Authentication. The JWT is stored in localStorage and
// decoded client-side only to read its claims for the UI (email/role) -
// the backend re-verifies the signature on every protected request, so
// trusting the decoded payload here is a display concern, not a security one.
import { API_URL } from './query'

const TOKEN_KEY = 'smart-traffic-ai-token'
const listeners = new Set()

/** Lets useAuth() re-render when login()/logout() change the session
 * elsewhere in the app, without a full page reload. */
export function subscribe(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

function notify() {
  for (const fn of listeners) fn()
}

function decodeJwtPayload(token) {
  try {
    const payload = token.split('.')[1]
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'))
    return JSON.parse(json)
  } catch {
    return null
  }
}

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* localStorage unavailable (private browsing etc) - session won't persist across reloads */
  }
}

/** Reads the current session from the stored token, or null if logged out
 * or the token has expired. */
export function getSession() {
  const token = getToken()
  if (!token) return null
  const payload = decodeJwtPayload(token)
  if (!payload) return null
  if (payload.exp && Date.now() / 1000 > payload.exp) {
    setToken(null)
    return null
  }
  return { token, email: payload.sub, role: payload.role, vehicleId: payload.vehicleId ?? null }
}

export async function login(email, password) {
  const res = await fetch(`${API_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) throw new Error('Invalid email or password')
  const data = await res.json()
  setToken(data.token)
  notify()
  return { email: data.email, role: data.role }
}

export function logout() {
  setToken(null)
  notify()
}
