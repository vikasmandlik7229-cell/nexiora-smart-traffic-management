// air_quality/air_quality_logs are public-read, and the controller view
// needs nothing extra beyond the public page - reuse it rather than
// maintaining a second copy of the same charts.
import PublicAirQuality from '../public/AirQuality'

export default function DashboardAirQuality() {
  return <PublicAirQuality />
}
