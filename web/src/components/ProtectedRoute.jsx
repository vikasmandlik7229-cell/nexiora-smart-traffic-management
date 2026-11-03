import { Navigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

/** Wraps a route element, requiring sign-in and (optionally) a specific role. */
export function ProtectedRoute({ children, role }) {
  const { user, role: userRole, loading } = useAuth()

  if (loading) {
    return <div className="flex min-h-[50vh] items-center justify-center text-slate-400">Loading...</div>
  }
  if (!user) return <Navigate to="/login" replace />
  if (role && userRole !== role) return <Navigate to="/access-denied" replace />

  return children
}
