const LIGHTS = ['red', 'yellow', 'green']
const LIT_COLOR = { red: 'bg-signal-red', yellow: 'bg-signal-amber', green: 'bg-signal-green' }
const GLOW = {
  red: 'shadow-[0_0_5px_1.5px_rgba(229,57,53,0.85)]',
  yellow: 'shadow-[0_0_5px_1.5px_rgba(255,179,0,0.85)]',
  green: 'shadow-[0_0_5px_1.5px_rgba(67,160,71,0.85)]',
}

/** A small traditional traffic-light icon (red/yellow/green stacked in a
 * dark housing, only the current one lit) for one lane. */
function MiniTrafficLight({ state }) {
  return (
    <span className="inline-flex flex-col items-center gap-[2px] rounded-[3px] bg-slate-800 px-[3px] py-[3px] dark:bg-black/60">
      {LIGHTS.map((color) => (
        <span
          key={color}
          className={`h-[6px] w-[6px] rounded-full ${
            state === color ? `${LIT_COLOR[color]} ${GLOW[color]}` : 'bg-slate-600'
          }`}
        />
      ))}
    </span>
  )
}

/** Honest compact summary of a junction's signal: one small traffic-light
 * icon per lane, each lit on that lane's real current colour. A single
 * shared light can't represent "3 lanes red, 1 green" (a real junction's
 * normal state) without being misleading - it ends up looking green almost
 * all the time, and red only in the rare all-blocked case, which reads as a
 * bug rather than the accident-mode indicator it actually is. */
export function SignalDots({ lanes }) {
  const entries = Object.entries(lanes || {})
  if (entries.length === 0) {
    return <span className="inline-block h-2.5 w-2.5 rounded-full bg-slate-300 dark:bg-slate-700" title="no live signal data" />
  }
  return (
    <span className="inline-flex items-center gap-1" title="One mini traffic light per lane - its real current red/yellow/green, not a single shared light">
      {entries.map(([laneId, lane]) => (
        <MiniTrafficLight key={laneId} state={lane.state} />
      ))}
    </span>
  )
}
