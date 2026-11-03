import { Inbox } from 'lucide-react'

export function EmptyState({ title = 'Nothing here yet', hint, icon: Icon = Inbox }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center text-slate-500 dark:text-slate-400">
      <Icon size={32} className="opacity-50" />
      <p className="font-medium">{title}</p>
      {hint && <p className="max-w-xs text-sm opacity-80">{hint}</p>}
    </div>
  )
}
