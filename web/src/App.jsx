import { Navigate, Route, Routes } from 'react-router-dom'
import { PublicLayout } from './layouts/PublicLayout'
import { DashboardLayout } from './layouts/DashboardLayout'
import { ProtectedRoute } from './components/ProtectedRoute'

import LiveOverview from './pages/public/LiveOverview'
import PublicSignals from './pages/public/Signals'
import PublicCityMap from './pages/public/CityMap'
import PublicPredictions from './pages/public/Predictions'
import PublicAirQuality from './pages/public/AirQuality'
import PublicAlerts from './pages/public/Alerts'
import Login from './pages/Login'
import Driver from './pages/Driver'
import AccessDenied from './pages/AccessDenied'

import CommandCentre from './pages/dashboard/CommandCentre'
import JunctionDetail from './pages/dashboard/JunctionDetail'
import CityMapDashboard from './pages/dashboard/CityMapDashboard'
import Emergencies from './pages/dashboard/Emergencies'
import Accidents from './pages/dashboard/Accidents'
import Violations from './pages/dashboard/Violations'
import DashboardPredictions from './pages/dashboard/DashboardPredictions'
import Performance from './pages/dashboard/Performance'
import DashboardAirQuality from './pages/dashboard/DashboardAirQuality'
import Reports from './pages/dashboard/Reports'
import Settings from './pages/dashboard/Settings'

export default function App() {
  return (
    <Routes>
      {/* Public portal */}
      <Route element={<PublicLayout />}>
        <Route path="/" element={<LiveOverview />} />
        <Route path="/signals" element={<PublicSignals />} />
        <Route path="/map" element={<PublicCityMap />} />
        <Route path="/predictions" element={<PublicPredictions />} />
        <Route path="/air" element={<PublicAirQuality />} />
        <Route path="/alerts" element={<PublicAlerts />} />
      </Route>

      <Route path="/login" element={<Login />} />
      <Route path="/access-denied" element={<AccessDenied />} />

      {/* Ambulance driver (role: driver) */}
      <Route
        path="/driver"
        element={
          <ProtectedRoute role="driver">
            <Driver />
          </ProtectedRoute>
        }
      />

      {/* Controller dashboard (role: controller) */}
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute role="controller">
            <DashboardLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<CommandCentre />} />
        <Route path="junction/:junctionId" element={<JunctionDetail />} />
        <Route path="map" element={<CityMapDashboard />} />
        <Route path="emergencies" element={<Emergencies />} />
        <Route path="accidents" element={<Accidents />} />
        <Route path="violations" element={<Violations />} />
        <Route path="predictions" element={<DashboardPredictions />} />
        <Route path="performance" element={<Performance />} />
        <Route path="air-quality" element={<DashboardAirQuality />} />
        <Route path="reports" element={<Reports />} />
        <Route path="settings" element={<Settings />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
