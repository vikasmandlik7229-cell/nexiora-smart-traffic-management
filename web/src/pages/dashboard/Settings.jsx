import { useState } from 'react'
import { limit } from '../../lib/query'
import { Cpu, Plus, Settings as SettingsIcon, Users } from 'lucide-react'
import { useCollection } from '../../hooks/useCollection'
import { useDoc } from '../../hooks/useDoc'
import { Card } from '../../components/Card'
import { Badge } from '../../components/Badge'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonCard } from '../../components/Skeleton'
import { saveAuthorisedVehicle, setVehicleActive } from '../../lib/vehicles'

function VehicleRow({ v }) {
  const [tagId, setTagId] = useState(v.tagId || '')
  const [saving, setSaving] = useState(false)

  async function saveTag() {
    if (tagId === v.tagId) return
    setSaving(true)
    try {
      await saveAuthorisedVehicle(v.id, { tagId })
    } finally {
      setSaving(false)
    }
  }

  async function toggleActive() {
    await setVehicleActive(v.id, !v.active)
  }

  return (
    <tr className="border-b border-slate-100 last:border-0 dark:border-slate-800">
      <td className="py-2 pr-4 font-medium text-slate-700 dark:text-slate-200">{v.id}</td>
      <td className="py-2 pr-4">{v.type}</td>
      <td className="py-2 pr-4">
        <input
          value={tagId}
          onChange={(e) => setTagId(e.target.value)}
          onBlur={saveTag}
          className="w-36 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-white"
        />
      </td>
      <td className="py-2 pr-4 text-slate-500 dark:text-slate-400">{v.hospital || v.driverName || '-'}</td>
      <td className="py-2 pr-4">
        <Badge variant={v.active ? 'success' : 'neutral'}>{v.active ? 'Active' : 'Inactive'}</Badge>
      </td>
      <td className="py-2">
        <button
          onClick={toggleActive}
          disabled={saving}
          className="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
        >
          {v.active ? 'Deactivate' : 'Activate'}
        </button>
      </td>
    </tr>
  )
}

function AddVehicleForm({ onAdded }) {
  const [form, setForm] = useState({ vehicleId: '', type: 'ambulance', tagId: '', hospital: '', driverName: '' })
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    try {
      await saveAuthorisedVehicle(form.vehicleId, {
        type: form.type, tagId: form.tagId, hospital: form.hospital || null,
        driverName: form.driverName || null, active: true,
      })
      setForm({ vehicleId: '', type: 'ambulance', tagId: '', hospital: '', driverName: '' })
      onAdded?.()
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-3 rounded-lg border border-dashed border-slate-300 p-3 sm:grid-cols-5 sm:items-end dark:border-slate-700">
      <input required placeholder="Vehicle ID" value={form.vehicleId} onChange={(e) => setForm({ ...form, vehicleId: e.target.value })} className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-white" />
      <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-white">
        <option value="ambulance">Ambulance</option>
        <option value="fire">Fire</option>
        <option value="police">Police</option>
      </select>
      <input required placeholder="RFID tag ID" value={form.tagId} onChange={(e) => setForm({ ...form, tagId: e.target.value })} className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-white" />
      <input placeholder="Hospital / station" value={form.hospital} onChange={(e) => setForm({ ...form, hospital: e.target.value })} className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-white" />
      <button type="submit" disabled={submitting} className="flex items-center justify-center gap-1.5 rounded-md bg-accent-600 py-1.5 text-sm font-medium text-white hover:bg-accent-700 disabled:opacity-60">
        <Plus size={14} /> {submitting ? 'Adding...' : 'Add vehicle'}
      </button>
    </form>
  )
}

export default function Settings() {
  const { data: vehicles, loading } = useCollection('authorised_vehicles', [limit(20)])
  const { data: users } = useCollection('users', [limit(50)])
  const { data: models } = useDoc('system', 'models')

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
        <SettingsIcon size={20} className="text-accent-500" />
        <h1 className="text-xl font-bold text-slate-800 dark:text-white">Settings</h1>
      </div>

      <Card title="Authorised vehicles">
        {vehicles.length === 0 ? (
          <EmptyState title="No authorised vehicles yet" hint="Run backend/db/seed.py, or add one below." />
        ) : (
          <div className="mb-4 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-400">
                <tr>
                  <th className="py-1.5 pr-4">Vehicle ID</th>
                  <th className="py-1.5 pr-4">Type</th>
                  <th className="py-1.5 pr-4">RFID tag</th>
                  <th className="py-1.5 pr-4">Hospital / driver</th>
                  <th className="py-1.5 pr-4">Status</th>
                  <th className="py-1.5"></th>
                </tr>
              </thead>
              <tbody>
                {vehicles.map((v) => <VehicleRow key={v.id} v={v} />)}
              </tbody>
            </table>
          </div>
        )}
        <AddVehicleForm />
      </Card>

      <Card title="Users and roles">
        <p className="mb-3 flex items-center gap-1.5 text-xs text-slate-400">
          <Users size={14} /> Role changes are operator-only, by design (the backend API has no endpoint for it).
          Run: <code className="font-mono">python -m db.seed --set-role someone@example.com controller somepassword</code>
        </p>
        {users.length === 0 ? (
          <EmptyState title="No users seen yet" hint="Users appear here after they've signed in at least once." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-400">
                <tr>
                  <th className="py-1.5 pr-4">Email</th>
                  <th className="py-1.5 pr-4">Role</th>
                  <th className="py-1.5">Vehicle</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {users.map((u) => (
                  <tr key={u.id}>
                    <td className="py-1.5 pr-4 text-slate-700 dark:text-slate-200">{u.email || u.id}</td>
                    <td className="py-1.5 pr-4"><Badge variant="neutral">{u.role || 'none'}</Badge></td>
                    <td className="py-1.5 text-slate-500 dark:text-slate-400">{u.vehicleId || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Deployed model">
        {!models ? (
          <EmptyState title="No model info yet" hint="Run backend/db/seed.py (writes system/models)." icon={Cpu} />
        ) : (
          <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
            <div>
              <p className="text-xs text-slate-400">Detector</p>
              <p className="font-semibold text-slate-700 dark:text-slate-200">{models.detectorName}</p>
            </div>
            <div>
              <p className="text-xs text-slate-400">Classes</p>
              <p className="font-semibold text-slate-700 dark:text-slate-200">{(models.classes || []).join(', ')}</p>
            </div>
            <div>
              <p className="text-xs text-slate-400">mAP50</p>
              <p className="font-semibold text-slate-700 dark:text-slate-200">{models.mAP50?.toFixed(3) ?? '-'}</p>
            </div>
            <div>
              <p className="text-xs text-slate-400">Emergency classifier</p>
              <p className="font-semibold text-slate-700 dark:text-slate-200">
                {models.emergencyClassifier ? 'Deployed' : 'Not trained (T4 skipped, no dataset - RFID priority used instead)'}
              </p>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
