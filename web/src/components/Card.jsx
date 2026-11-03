export function Card({ children, className = '', title, action }) {
  return (
    <div
      className={`rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900 ${className}`}
    >
      {(title || action) && (
        <div className="mb-3 flex items-center justify-between">
          {title && <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">{title}</h3>}
          {action}
        </div>
      )}
      {children}
    </div>
  )
}
