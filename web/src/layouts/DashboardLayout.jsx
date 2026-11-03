import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { limit, orderBy } from '../lib/query'
import {
  AlertTriangle,
  Ambulance,
  BarChart3,
  Bell,
  CloudFog,
  FileText,
  Gauge,
  LayoutDashboard,
  LogOut,
  Map,
  MapPin,
  Menu,
  Moon,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Sun,
  TrafficCone,
  TrendingUp,
  WifiOff,
} from 'lucide-react'
import { logout } from '../lib/auth'
import { markAlertsRead } from '../lib/alerts'
import { useAuth } from '../hooks/useAuth'
import { useTheme } from '../hooks/useTheme'
import { useBackendHealth } from '../hooks/useBackendHealth'
import { useCollection } from '../hooks/useCollection'
import { AlertItem } from '../components/AlertItem'
import { EmptyState } from '../components/EmptyState'

const NAV_ITEMS = [
  { to: '/dashboard', label: 'Overview', pageTitle: 'Command Center', icon: LayoutDashboard, end: true },
  { to: '/dashboard/junction/J1', label: 'Live Traffic & Signals', pageTitle: 'Live Traffic & Adaptive Signal Control', icon: Gauge },
  { to: '/dashboard/map', label: 'City Map', pageTitle: 'City Map', icon: Map },
  { to: '/dashboard/predictions', label: 'AI Traffic Prediction', pageTitle: 'AI Traffic Prediction', icon: TrendingUp },
  { to: '/dashboard/emergencies', label: 'Ambulance Green Corridor', pageTitle: 'Ambulance Green Corridor', icon: Ambulance },
  { to: '/dashboard/accidents', label: 'Accident Detection & Alerts', pageTitle: 'Accident Detection & Alerts', icon: AlertTriangle },
  { to: '/dashboard/violations', label: 'Traffic Violation Detection', pageTitle: 'Traffic Violation Detection', icon: ShieldAlert },
  { to: '/dashboard/air-quality', label: 'Air Quality Monitoring', pageTitle: 'Air Quality Monitoring', icon: CloudFog },
  { to: '/dashboard/performance', label: 'Performance', pageTitle: 'Adaptive vs Fixed-Time Performance', icon: BarChart3 },
  { to: '/dashboard/reports', label: 'Reports & Analytics', pageTitle: 'Reports & Analytics', icon: FileText },
  { to: '/dashboard/settings', label: 'Settings', pageTitle: 'Settings', icon: Settings },
]

function useClock() {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return now
}

function pageTitleFor(pathname) {
  const match = [...NAV_ITEMS].sort((a, b) => b.to.length - a.to.length).find((item) => pathname.startsWith(item.to))
  return match?.pageTitle || 'Smart Traffic AI'
}

export function DashboardLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [bellOpen, setBellOpen] = useState(false)
  const { theme, toggleTheme } = useTheme()
  const { user, role } = useAuth()
  const healthy = useBackendHealth()
  const now = useClock()
  const navigate = useNavigate()
  const location = useLocation()
  const { data: alerts } = useCollection('alerts', [orderBy('timestamp', 'desc'), limit(20)])
  const unreadCount = alerts.filter((a) => !a.read).length

  function handleLogout() {
    logout()
    navigate('/login')
  }

  function toggleBell() {
    const opening = !bellOpen
    setBellOpen(opening)
    if (opening) {
      const unreadIds = alerts.filter((a) => !a.read).map((a) => a.id)
      if (unreadIds.length) markAlertsRead(unreadIds).catch(() => {})
    }
  }

  return (
    <div className="flex min-h-screen bg-slate-50 dark:bg-slate-950">
      {mobileOpen && (
        <div className="fixed inset-0 z-30 bg-black/50 sm:hidden" onClick={() => setMobileOpen(false)} />
      )}

      {/* Fixed dark-navy sidebar - a deliberate brand colour, not theme-toggled */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col bg-navy-900 text-slate-200 transition-transform sm:static sm:z-auto sm:translate-x-0 sm:transition-all ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        } ${collapsed ? 'sm:w-16' : 'sm:w-64'}`}
      >
        <div className="flex items-center gap-2.5 border-b border-white/10 px-4 py-4">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-600">
            <TrafficCone size={18} className="text-white" />
          </span>
          {!collapsed && (
            <div className="min-w-0">
              <p className="truncate text-sm font-bold leading-tight text-white">Smart Traffic AI</p>
              <p className="truncate text-[10px] leading-tight text-slate-400">Intelligent Traffic. Safer Roads.</p>
            </div>
          )}
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto p-2">
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={() => setMobileOpen(false)}
              title={collapsed ? label : undefined}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive ? 'bg-accent-600 text-white' : 'text-slate-300 hover:bg-white/5 hover:text-white'
                }`
              }
            >
              <Icon size={18} className="shrink-0" />
              {!collapsed && <span className="truncate">{label}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-white/10 p-3">
          <div className="flex items-center gap-2.5 rounded-lg px-1 py-1">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-600/20 text-accent-300">
              <ShieldCheck size={16} />
            </span>
            {!collapsed && (
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-white">{user?.email || 'Traffic Controller'}</p>
                <p className="truncate text-xs capitalize text-slate-400">{role || 'Administrator'}</p>
              </div>
            )}
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {healthy === false && (
          <div className="flex items-center justify-center gap-2 bg-red-600 px-4 py-1.5 text-sm font-medium text-white">
            <WifiOff size={14} /> Backend offline - live video, evidence and reports are unavailable right now.
          </div>
        )}

        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMobileOpen((o) => !o)}
              className="rounded-md p-2 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800 sm:hidden"
              aria-label="Toggle menu"
            >
              <Menu size={18} />
            </button>
            <button
              onClick={() => setCollapsed((c) => !c)}
              className="hidden rounded-md p-2 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800 sm:block"
              aria-label="Toggle sidebar"
            >
              <Menu size={18} />
            </button>
            <div>
              <h1 className="text-base font-bold text-navy-800 dark:text-white">{pageTitleFor(location.pathname)}</h1>
              <p className="hidden items-center gap-1 text-xs text-slate-400 sm:flex">
                <MapPin size={11} /> Demo network - 4 junctions
                <span className="mx-1">-</span>
                <span className={`inline-flex items-center gap-1 font-medium ${healthy ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${healthy ? 'bg-green-500' : 'bg-red-500'}`} />
                  {healthy ? 'Backend online' : 'Backend offline'}
                </span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <span className="hidden text-sm font-mono tabular-nums text-slate-500 dark:text-slate-400 sm:inline">
              {now.toLocaleDateString([], { day: '2-digit', month: 'short' })} - {now.toLocaleTimeString()}
            </span>
            <div className="relative">
              <button
                onClick={toggleBell}
                className="relative rounded-md p-2 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
                aria-label="Notifications"
              >
                <Bell size={18} />
                {unreadCount > 0 && (
                  <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
                    {unreadCount > 9 ? '9+' : unreadCount}
                  </span>
                )}
              </button>
              {bellOpen && (
                <>
                  {/* Invisible full-screen backdrop, closes the dropdown on an outside click - same pattern as the mobile sidebar above */}
                  <div className="fixed inset-0 z-40" onClick={() => setBellOpen(false)} />
                  <div className="absolute right-0 z-50 mt-2 max-h-96 w-80 overflow-y-auto rounded-lg border border-slate-200 bg-white p-3 shadow-lg dark:border-slate-700 dark:bg-slate-900">
                    <p className="mb-1 px-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Notifications</p>
                    {alerts.length === 0 ? (
                      <EmptyState title="No alerts yet" />
                    ) : (
                      alerts.map((alert) => <AlertItem key={alert.id} alert={alert} />)
                    )}
                  </div>
                </>
              )}
            </div>
            <button
              onClick={toggleTheme}
              className="rounded-md p-2 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
              aria-label="Toggle theme"
            >
              {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <span className="hidden text-sm text-slate-600 dark:text-slate-300 sm:inline">{user?.email}</span>
            <button
              onClick={handleLogout}
              className="flex items-center gap-1 rounded-md px-2 py-1.5 text-sm text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
            >
              <LogOut size={16} />
              <span className="hidden sm:inline">Logout</span>
            </button>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-4">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
