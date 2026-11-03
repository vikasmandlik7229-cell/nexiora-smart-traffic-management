import { NavLink, Outlet } from 'react-router-dom'
import { Moon, Sun, TrafficCone, WifiOff } from 'lucide-react'
import { useTheme } from '../hooks/useTheme'
import { useBackendHealth } from '../hooks/useBackendHealth'

const NAV_ITEMS = [
  { to: '/', label: 'Overview', end: true },
  { to: '/signals', label: 'Signals' },
  { to: '/map', label: 'City Map' },
  { to: '/predictions', label: 'Predictions' },
  { to: '/air', label: 'Air Quality' },
  { to: '/alerts', label: 'Alerts' },
]

function NavItem({ to, label, end }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
          isActive
            ? 'bg-accent-100 text-accent-700 dark:bg-accent-500/15 dark:text-accent-300'
            : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
        }`
      }
    >
      {label}
    </NavLink>
  )
}

export function PublicLayout() {
  const { theme, toggleTheme } = useTheme()
  const healthy = useBackendHealth()

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      {healthy === false && (
        <div className="flex items-center justify-center gap-2 bg-red-600 px-4 py-1.5 text-sm font-medium text-white">
          <WifiOff size={14} /> Backend offline - live video, evidence and reports are unavailable right now.
        </div>
      )}

      <header className="border-b border-slate-200 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-900/80">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-600">
              <TrafficCone size={18} className="text-white" />
            </span>
            <div className="leading-tight">
              <p className="font-bold text-slate-900 dark:text-white">Smart Traffic AI</p>
              <p className="hidden text-[10px] text-slate-400 sm:block">Intelligent Traffic. Safer Roads. Smarter Cities.</p>
            </div>
          </div>
          <nav className="hidden flex-1 items-center justify-center gap-1 md:flex">
            {NAV_ITEMS.map((item) => (
              <NavItem key={item.to} {...item} />
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <button
              onClick={toggleTheme}
              className="rounded-md p-2 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
              aria-label="Toggle theme"
            >
              {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <NavLink
              to="/login"
              className="rounded-md bg-accent-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-accent-700"
            >
              Login
            </NavLink>
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto border-t border-slate-100 px-4 py-2 md:hidden dark:border-slate-800">
          {NAV_ITEMS.map((item) => (
            <NavItem key={item.to} {...item} />
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
