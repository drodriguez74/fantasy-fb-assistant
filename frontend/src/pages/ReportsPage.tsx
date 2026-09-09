import { Link } from 'react-router-dom'
import {
  ClipboardDocumentCheckIcon,
  ClockIcon,
  ChartBarIcon,
  ArrowRightIcon,
} from '@heroicons/react/24/outline'

/**
 * Reports hub — the "look back" surfaces that don't belong in the weekly
 * in-season flow (This Week / Waivers / Trades). Post-Draft Analysis, Draft
 * History, and Historical Performance each keep their own route; this page
 * is just the shared entry point they're grouped under in the navbar.
 */
const REPORTS = [
  {
    to: '/post-draft',
    icon: ClipboardDocumentCheckIcon,
    title: 'Post-Draft Analysis',
    body: 'How your roster came out of the draft — positional depth, value hits and reaches, where to shore up.',
  },
  {
    to: '/draft-history',
    icon: ClockIcon,
    title: 'Draft History',
    body: 'Every past draft session you ran, with its grade and the roster you walked away with.',
  },
  {
    to: '/historical',
    icon: ChartBarIcon,
    title: 'Historical Performance',
    body: 'Multi-season scoring, consistency, boom/bust rates and career trends for any player.',
  },
] as const

export function ReportsPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-display text-3xl font-bold uppercase tracking-tight text-body">
          Reports
        </h1>
        <p className="mt-1 text-sm text-muted">
          Look back at how things went — draft grades, past sessions, and long-run player history.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-px border border-hairline bg-hairline md:grid-cols-3">
        {REPORTS.map(({ to, icon: Icon, title, body }) => (
          <Link
            key={to}
            to={to}
            className="group bg-surface p-6 transition-colors hover:bg-surface-2"
          >
            <div className="flex h-11 w-11 items-center justify-center border border-line text-accent-ink">
              <Icon className="h-5 w-5" />
            </div>
            <h2 className="mt-4 font-display text-xl font-bold uppercase tracking-tight text-body">
              {title}
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-muted">{body}</p>
            <p className="mt-4 flex items-center gap-1 font-stat text-xs font-medium text-accent-ink">
              Open
              <ArrowRightIcon className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </p>
          </Link>
        ))}
      </div>
    </div>
  )
}
