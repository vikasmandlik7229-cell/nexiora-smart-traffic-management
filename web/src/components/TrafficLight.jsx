import { useCountdown } from '../hooks/useCountdown'

const SIZES = {
  sm: { box: 'w-10 p-1 gap-1', dot: 'h-2.5 w-2.5' },
  md: { box: 'w-14 p-1.5 gap-1.5', dot: 'h-3.5 w-3.5' },
  lg: { box: 'w-20 p-2 gap-2', dot: 'h-5 w-5' },
}

const COLORS = {
  red: { on: 'bg-signal-red shadow-[0_0_10px_2px] shadow-signal-red/60', off: 'bg-red-950/40' },
  yellow: { on: 'bg-signal-amber shadow-[0_0_10px_2px] shadow-signal-amber/60', off: 'bg-amber-950/40' },
  green: { on: 'bg-signal-green shadow-[0_0_10px_2px] shadow-signal-green/60', off: 'bg-green-950/40' },
}

/** state: "red" | "yellow" | "green". phaseEndsAt: unix seconds (optional). */
export function TrafficLight({ state, phaseEndsAt, size = 'md', label }) {
  const remaining = useCountdown(phaseEndsAt)
  const sizing = SIZES[size] || SIZES.md

  return (
    <div className="flex flex-col items-center gap-1">
      <div className={`flex flex-col items-center rounded-lg bg-slate-800 ${sizing.box}`}>
        {['red', 'yellow', 'green'].map((c) => (
          <span
            key={c}
            className={`rounded-full transition-colors duration-300 ${sizing.dot} ${
              state === c ? COLORS[c].on : COLORS[c].off
            }`}
          />
        ))}
      </div>
      {label && <span className="text-xs font-medium text-slate-500 dark:text-slate-400">{label}</span>}
      {remaining !== null && (
        <span className="text-sm font-mono font-semibold tabular-nums text-slate-700 dark:text-slate-200">
          {remaining}s
        </span>
      )}
    </div>
  )
}
