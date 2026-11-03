export function PagePlaceholder({ title }) {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-2 text-center">
      <h1 className="text-2xl font-bold text-slate-800 dark:text-white">{title}</h1>
      <p className="text-slate-500 dark:text-slate-400">Built in a later phase (Prompt 11b-11f).</p>
    </div>
  )
}
