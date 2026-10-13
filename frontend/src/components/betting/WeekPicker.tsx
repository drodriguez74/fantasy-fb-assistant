// One week at a time: "‹ Week 5 ›" with a This week reset (2026-10-12 review:
// chips wrapped onto several rows by late season). The page holds the picked
// week, so Shows, My entries and the Audit stay on the same one across tabs.
import { type BetWeek, sameWeek } from './betTypes'

export function WeekPicker({
  weeks,
  value,
  current,
  onChange,
}: {
  // Newest first.
  weeks: BetWeek[]
  value: BetWeek | null
  current: BetWeek | null
  onChange: (w: BetWeek) => void
}) {
  if (weeks.length === 0) return null
  const i = Math.max(0, weeks.findIndex((w) => sameWeek(w, value)))
  const shown = weeks[i]
  const older = weeks[i + 1]
  const newer = weeks[i - 1]
  const isCurrent = sameWeek(shown, current)
  const step = 'px-2 py-1 rounded-md text-body disabled:text-faint disabled:cursor-default hover:bg-surface-2'
  return (
    <div className="flex items-center gap-2 text-xs" aria-label="Week">
      <div className="flex items-center rounded-lg border border-hairline">
        <button onClick={() => older && onChange(older)} disabled={!older} aria-label="Earlier week" className={step}>
          ‹
        </button>
        <span className="stat-nums px-2 text-body font-medium min-w-[6.5rem] text-center">
          {isCurrent ? `This week (${shown.week})` : `Week ${shown.week}`}
        </span>
        <button onClick={() => newer && onChange(newer)} disabled={!newer} aria-label="Later week" className={step}>
          ›
        </button>
      </div>
      {!isCurrent && current && weeks.some((w) => sameWeek(w, current)) && (
        <button onClick={() => onChange(current)} className="text-muted underline hover:text-body">
          This week
        </button>
      )}
    </div>
  )
}
