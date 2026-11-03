// Predictions data (predictions/short_predictions) is public-read, and the
// controller view needs nothing extra beyond the public page - reuse it
// rather than maintaining a second copy of the same charts.
import PublicPredictions from '../public/Predictions'

export default function DashboardPredictions() {
  return <PublicPredictions />
}
