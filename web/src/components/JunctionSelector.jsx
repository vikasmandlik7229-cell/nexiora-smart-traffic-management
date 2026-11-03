/** Shared junction-picker pill row, used by every public page that lets you
 * switch which junction you're looking at. */
export function JunctionSelector({ junctions, selected, onSelect }) {
  return (
    <div className="flex flex-wrap gap-2">
      {junctions.map((j) => (
        <button
          key={j.id}
          onClick={() => onSelect(j.id)}
          className={`rounded-md px-3 py-1.5 text-sm font-medium transition-all ${
            j.id === selected
              ? 'bg-accent-600 text-white shadow-sm'
              : 'bg-white text-slate-600 hover:bg-slate-100 hover:shadow-sm dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800'
          }`}
        >
          {j.id}
        </button>
      ))}
    </div>
  )
}
