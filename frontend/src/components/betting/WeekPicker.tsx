// Week chips for lists that show one betting week at a time (newest first).
import { type BetWeek, sameWeek, weekKey } from './betTypes'

export function WeekPicker({
  weeks,
  value,
  current,
  onChange,
}: {
  weeks: BetWeek[]
  value: BetWeek | null
  current: BetWeek | null
  onChange: (w: BetWeek) => void
}) {
  if (weeks.length === 0) return null
  return (
    <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Week">
      {weeks.map((w) => (
        <button
          key={weekKey(w)}
          role="tab"
          aria-selected={sameWeek(w, value)}
          onClick={() => onChange(w)}
          className={`rounded-md px-2.5 py-1 text-xs ${
            sameWeek(w, value) ? 'bg-surface-2 text-body font-medium' : 'border border-hairline text-muted hover:text-body'
          }`}
        >
          {sameWeek(w, current) ? `This week (${w.week})` : `Week ${w.week}`}
        </button>
      ))}
    </div>
  )
}
