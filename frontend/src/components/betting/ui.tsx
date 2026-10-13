// Shared pieces for the Bets page (2026-10-12 review: ten components had each
// grown their own toggle, section header, status badge and always-on help
// paragraph). One look everywhere; nothing here pulls in a library.
import { useState, type ReactNode } from 'react'

/** A two-to-four option switch (sport, Games/Props, Power/Flex, ...). */
export function Segmented<T extends string | boolean>({
  label,
  value,
  options,
  onChange,
  size = 'sm',
}: {
  label: string
  value: T
  options: [T, string][]
  onChange: (v: T) => void
  size?: 'sm' | 'md'
}) {
  return (
    <div className="flex w-fit rounded-lg border border-hairline p-0.5" role="tablist" aria-label={label}>
      {options.map(([v, text]) => (
        <button
          key={String(v)}
          role="tab"
          aria-selected={value === v}
          onClick={() => onChange(v)}
          className={`rounded-md ${size === 'md' ? 'px-3 py-1.5 text-sm' : 'px-2.5 py-1 text-xs'} ${
            value === v ? 'bg-surface-2 text-body font-medium' : 'text-muted'
          }`}
        >
          {text}
        </button>
      ))}
    </div>
  )
}

/** A section's title, with an optional one-line summary and an action on the right. */
export function SectionHeader({ title, meta, action }: { title: ReactNode; meta?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
      <h3 className="font-display font-bold uppercase tracking-tight text-sm text-body">{title}</h3>
      {(meta || action) && (
        <div className="flex items-baseline gap-3">
          {meta && <span className="text-xs text-muted">{meta}</span>}
          {action}
        </div>
      )}
    </div>
  )
}

/** Help text read once, then in the way: folded behind "How to read this". */
export function Explainer({ children, label = 'How to read this' }: { children: ReactNode; label?: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="text-xs">
      <button onClick={() => setOpen(!open)} aria-expanded={open} className="text-faint hover:text-muted">
        ⓘ {open ? 'Hide' : label}
      </button>
      {open && <div className="mt-1 text-muted leading-relaxed space-y-1">{children}</div>}
    </div>
  )
}

const STATUS_STYLE: Record<string, string> = {
  won: 'bg-success-100 text-success-800',
  lost: 'bg-danger-100 text-danger-800',
  partial: 'bg-highlight text-accent-ink',
}

/** A graded result: Won / Lost / Partial / Pending / Push / Refunded / Void. */
export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`stat-nums shrink-0 text-xs px-1.5 py-0.5 rounded ${STATUS_STYLE[status] ?? 'bg-surface-2 text-muted'}`}>
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  )
}
