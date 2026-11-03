import { AlertTriangle } from 'lucide-react'

export function ErrorState({ message = 'Something went wrong.' }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center text-red-500">
      <AlertTriangle size={32} />
      <p className="font-medium">{message}</p>
    </div>
  )
}
