import { Link } from 'react-router-dom'
import { ShieldAlert } from 'lucide-react'

export default function AccessDenied() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 text-center">
      <ShieldAlert size={40} className="text-red-500" />
      <h1 className="text-xl font-bold text-slate-800 dark:text-white">Access denied</h1>
      <p className="text-slate-500 dark:text-slate-400">You don't have permission to view this page.</p>
      <Link to="/" className="mt-2 rounded-md bg-accent-600 px-4 py-2 text-sm font-semibold text-white hover:bg-accent-700">
        Back to home
      </Link>
    </div>
  )
}
