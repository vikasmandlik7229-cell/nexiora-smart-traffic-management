import { useEffect, useMemo, useState } from 'react'
import { limit } from '../../lib/query'
import { Download, FileText } from 'lucide-react'
import { Line, LineChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useCollection } from '../../hooks/useCollection'
import { Card } from '../../components/Card'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonCard } from '../../components/Skeleton'
import { fetchReports, reportUrl } from '../../api'

function num(summary, key) {
  const v = parseFloat(summary?.[key])
  return Number.isFinite(v) ? v : null
}

function downloadCsv(filename, rows) {
  const csv = rows.map((r) => r.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function ReportLink({ filename }) {
  const [url, setUrl] = useState(null)
  useEffect(() => {
    let cancelled = false
    reportUrl(filename).then((u) => !cancelled && setUrl(u))
    return () => { cancelled = true }
  }, [filename])
  return (
    <a href={url || '#'} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-accent-600 hover:underline dark:text-accent-400">
      <Download size={12} /> {filename}
    </a>
  )
}

export default function Reports() {
  const { data: dailyReports, loading } = useCollection('daily_reports', [limit(30)])
  const [allFiles, setAllFiles] = useState([])
  const [filesError, setFilesError] = useState(false)

  useEffect(() => {
    fetchReports().then((r) => setAllFiles(r.reports || [])).catch(() => setFilesError(true))
  }, [])

  const sorted = useMemo(() => [...dailyReports].sort((a, b) => a.id.localeCompare(b.id)), [dailyReports])

  const trend = useMemo(
    () =>
      sorted.map((r) => ({
        date: r.id,
        adaptive: num(r.summary, 'Avg wait, adaptive (s)'),
        fixed: num(r.summary, 'Avg wait, fixed-time (s)'),
      })),
    [sorted],
  )

  function exportSummaryCsv(report) {
    const rows = [['Metric', 'Value'], ...Object.entries(report.summary || {})]
    downloadCsv(`${report.id}_summary.csv`, rows)
  }

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <FileText size={20} className="text-accent-500" />
        <h1 className="text-xl font-bold text-slate-800 dark:text-white">Reports</h1>
      </div>

      {dailyReports.length === 0 ? (
        <EmptyState
          title="No daily reports yet"
          hint="Run: python -m reports.daily_report --date YYYY-MM-DD  (or --range START END, or --demo-data for a full week of realistic records)."
        />
      ) : (
        <>
          <Card title="Wait-time trend across reports">
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={trend}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-800" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 11 }} unit="s" />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="adaptive" name="Adaptive" stroke="#43A047" strokeWidth={2} connectNulls />
                <Line type="monotone" dataKey="fixed" name="Fixed-time" stroke="#94a3b8" strokeWidth={2} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </Card>

          <Card title="Daily / range summaries">
            <div className="space-y-4">
              {sorted.slice().reverse().map((r) => (
                <div key={r.id} className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="font-semibold text-slate-700 dark:text-slate-200">{r.id}</span>
                    <div className="flex items-center gap-3 text-xs">
                      {r.pdfFile && <ReportLink filename={r.pdfFile} />}
                      <button onClick={() => exportSummaryCsv(r)} className="flex items-center gap-1 text-accent-600 hover:underline dark:text-accent-400">
                        <Download size={12} /> export CSV
                      </button>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
                    {Object.entries(r.summary || {}).map(([k, v]) => (
                      <div key={k} className="flex justify-between gap-2 sm:block">
                        <span className="text-xs text-slate-400">{k}</span>
                        <span className="font-medium text-slate-700 dark:text-slate-200">{v}</span>
                      </div>
                    ))}
                  </div>
                  {(r.csvFiles || []).length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-3 text-xs">
                      {r.csvFiles.map((f) => <ReportLink key={f} filename={f} />)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Card>
        </>
      )}

      <Card title="All report files (backend/reports/output)">
        {filesError ? (
          <EmptyState title="Can't reach the backend API" hint="Start backend/api/server.py (or run backend/main.py once Phase 12 wires it in)." />
        ) : allFiles.length === 0 ? (
          <EmptyState title="No report files on disk yet" />
        ) : (
          <ul className="grid grid-cols-1 gap-1.5 text-sm sm:grid-cols-2 lg:grid-cols-3">
            {allFiles.map((f) => (
              <li key={f}><ReportLink filename={f} /></li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
