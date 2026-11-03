import { useEffect, useState } from 'react'
import { getSession, subscribe } from '../lib/auth'

/** Current local session (email + role), decoded from the stored JWT.
 * Unlike the old Firestore-backed version, a role change made by an
 * operator (db/seed.py --set-role) requires the affected user to log in
 * again to pick it up - acceptable since that's already a rare, manual,
 * operator-only action. */
export function useAuth() {
  const [session, setSession] = useState(() => getSession())
  const [loading, setLoading] = useState(false)

  useEffect(() => subscribe(() => setSession(getSession())), [])

  return {
    user: session ? { email: session.email } : null,
    role: session?.role ?? null,
    vehicleId: session?.vehicleId ?? null,
    loading,
  }
}
