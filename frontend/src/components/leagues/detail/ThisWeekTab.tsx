import type { Dispatch, SetStateAction } from 'react'
import { BoltIcon, CheckCircleIcon, ClockIcon, InformationCircleIcon } from '@heroicons/react/24/outline'
import { DataConfidenceBadge } from '../../common/DataConfidenceBadge'
import { PlayerAvatar } from '../../players/PlayerAvatar'
import { formatStatusLabel, getStatusColor, getPositionColor, confidenceBadge, startSitBadge } from './display'
import { relTime, pairBySlot, type WaiverRecommendation, type ThisWeekPlayer, type ThisWeekMatchupSide, type ThisWeekData, type H2HRow, type LeagueTab } from './types'

interface ThisWeekTabProps {
  setActiveTab: Dispatch<SetStateAction<LeagueTab>>
  waiverRecs: WaiverRecommendation | null
  thisWeek: ThisWeekData
  showOptimal: boolean
  setShowOptimal: Dispatch<SetStateAction<boolean>>
  lineupView: 'mine' | 'matchup'
  setLineupView: Dispatch<SetStateAction<'mine' | 'matchup'>>
}

export function ThisWeekTab({ setActiveTab, waiverRecs, thisWeek, showOptimal, setShowOptimal, lineupView, setLineupView }: ThisWeekTabProps) {
  const m = thisWeek.matchup!
  const opt = thisWeek.optimization
  const lineup = thisWeek.lineup ?? []
  const BENCH = new Set(['BE', 'IR', 'BENCH', ''])
  const starters = lineup.filter((p) => !BENCH.has((p.slot_position || '').toUpperCase()))
  const bench = lineup.filter((p) => (p.slot_position || '').toUpperCase() !== 'IR' && BENCH.has((p.slot_position || '').toUpperCase()))
  const ir = lineup.filter((p) => (p.slot_position || '').toUpperCase() === 'IR')
  const oppLineup = thisWeek.opponent_lineup ?? []
  const oppStarters = oppLineup.filter((p) => !BENCH.has((p.slot_position || '').toUpperCase()))
  const oppBench = oppLineup.filter((p) => (p.slot_position || '').toUpperCase() !== 'IR' && BENCH.has((p.slot_position || '').toUpperCase()))
  const h2hStarterRows = pairBySlot(starters, oppStarters)
  const h2hBenchRows = pairBySlot(bench, oppBench)
  const swapOutNames = new Set((opt?.swaps ?? []).map((s) => s.bench_out.name))
  const swapInNames = new Set((opt?.swaps ?? []).map((s) => s.start_in.name))
  const startSitByName = new Map((thisWeek.start_sit ?? []).map((c) => [c.name, c]))
  const rec = (side: ThisWeekMatchupSide) =>
    side.wins != null ? `${side.wins}–${side.losses}${side.ties ? `–${side.ties}` : ''}` : null
  const fmtRank = (n?: number) => (n ? `#${n}` : null)
  // Field-position marker: 0 = dead even, clamp the projected margin to
  // a +/-30 pt visual range so a blowout projection doesn't peg the
  // marker off the bar.
  const margin = m.projected_margin || 0
  const markerPct = 50 + Math.max(-30, Math.min(30, margin)) / 30 * 42

  const renderRow = (p: ThisWeekPlayer, isBench: boolean) => {
    const flaggedOut = swapOutNames.has(p.name)
    const flaggedIn = swapInNames.has(p.name)
    const highlight = showOptimal && (flaggedOut || flaggedIn)
    const injured = !['ACTIVE', 'NORMAL', 'HEALTHY', ''].includes((p.injury_status || '').toUpperCase())
    return (
      <div
        key={`tw-${isBench ? 'bn' : 'st'}-${p.name}`}
        className={`grid grid-cols-[3rem_1fr_auto] sm:grid-cols-[3.5rem_1fr_6rem_4rem_4rem] items-center gap-2 px-3 py-2.5 border-b border-hairline text-sm ${
          highlight ? 'bg-highlight border-l-2 border-l-volt' : ''
        }`}
      >
        <span className="stat-nums text-xs text-muted">{(p.slot_position || '').toUpperCase()}</span>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <PlayerAvatar
              playerId={p.player_id}
              name={p.name}
              position={p.position}
              team={p.team}
              size={30}
            />
            <span className={`shrink-0 hidden sm:inline-flex items-center justify-center w-8 h-5 rounded text-[10px] font-semibold ${getPositionColor(p.position)}`}>
              {p.position || '—'}
            </span>
            <span className="font-medium text-body truncate">{p.name}</span>
            {p.team && (
              <span className="shrink-0 stat-nums text-[11px] text-faint">{p.team}</span>
            )}
            {injured && (
              <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium ${getStatusColor(p.injury_status)}`}>
                {formatStatusLabel(p.injury_status)}
              </span>
            )}
            {!isBench && startSitBadge(startSitByName.get(p.name))}
          </div>
          <div className="sm:hidden stat-nums text-[11px] text-faint mt-0.5 pl-[38px]">
            {p.pro_opponent || (p.on_bye ? 'BYE' : '')}
            {p.game_played ? ` · ${p.points?.toFixed(1) ?? '0.0'} actual` : ''}
          </div>
          {showOptimal && flaggedOut && (
            <p className="stat-nums text-[11px] text-accent-ink mt-1">
              &#9662; bench &mdash; swap in {(opt?.swaps ?? []).find((s) => s.bench_out.name === p.name)?.start_in.name}
            </p>
          )}
          {showOptimal && flaggedIn && (
            <p className="stat-nums text-[11px] text-accent-ink mt-1">&#9656; start at {(opt?.swaps ?? []).find((s) => s.start_in.name === p.name)?.slot}</p>
          )}
        </div>
        <span className="hidden sm:block stat-nums text-xs text-muted">
          {p.pro_opponent || (p.on_bye ? 'BYE' : '—')}
        </span>
        <span className="stat-nums text-sm text-muted text-right tabular-nums">
          {p.projected_points != null ? p.projected_points.toFixed(1) : '—'}
        </span>
        <span className="stat-nums text-sm text-body text-right tabular-nums font-medium">
          {p.game_played ? (p.points ?? 0).toFixed(1) : '—'}
        </span>
      </div>
    )
  }

  const h2hCell = (p: ThisWeekPlayer | undefined, side: 'mine' | 'theirs') => {
    if (!p) return <div />
    const injured = !['ACTIVE', 'NORMAL', 'HEALTHY', ''].includes((p.injury_status || '').toUpperCase())
    const flipped = side === 'theirs'
    return (
      <div className={`min-w-0 flex items-center gap-1.5 ${flipped ? 'flex-row-reverse text-right' : ''}`}>
        <PlayerAvatar playerId={p.player_id} name={p.name} position={p.position} team={p.team} size={24} className="shrink-0" />
        <div className="min-w-0">
          <div className={`flex items-center gap-1 ${flipped ? 'flex-row-reverse' : ''}`}>
            <span className="text-xs font-medium text-body truncate">{p.name}</span>
            {injured && (
              <span className={`shrink-0 text-[9px] px-1 rounded font-medium ${getStatusColor(p.injury_status)}`}>
                {formatStatusLabel(p.injury_status)}
              </span>
            )}
          </div>
          <div className={`stat-nums text-[10px] text-muted flex items-center gap-1 ${flipped ? 'flex-row-reverse' : ''}`}>
            <span>{p.team || '—'}</span>
            <span className="text-faint">&middot;</span>
            <span className={p.game_played ? 'text-body font-medium' : ''}>
              {p.game_played ? (p.points ?? 0).toFixed(1) : `${p.projected_points != null ? p.projected_points.toFixed(1) : '—'}p`}
            </span>
          </div>
        </div>
      </div>
    )
  }

  const renderH2HRow = (row: H2HRow, idx: number) => (
    <div key={`h2h-${row.slot}-${idx}`} className="grid grid-cols-[1fr_2.25rem_1fr] items-center gap-1.5 px-2 sm:px-3 py-2 border-b border-hairline">
      {h2hCell(row.mine, 'mine')}
      <span className="stat-nums text-[9px] text-faint text-center">{row.slot === 'RB/WR/TE' || row.slot === 'FLEX' || row.slot === 'OP' ? 'FLX' : row.slot}</span>
      {h2hCell(row.theirs, 'theirs')}
    </div>
  )

  return (
    <div className="space-y-6">
      {thisWeek._cache && (
        <div className="flex items-center gap-2 stat-nums text-[10px] tracking-wider text-faint -mb-2">
          <span>UPDATED {relTime(thisWeek._cache.as_of).toUpperCase()}</span>
          {thisWeek._cache.stale && (
            <span className="inline-flex items-center gap-1 text-accent-ink">
              <ClockIcon className="h-3 w-3 animate-spin" /> SYNCING
            </span>
          )}
        </div>
      )}
      {/* MATCHUP SCOREBOARD */}
      <div className="bg-surface rounded-lg border border-hairline overflow-hidden">
        <div className="p-4 sm:p-6">
          <div className="grid grid-cols-[1fr_auto_1fr] items-start gap-3 sm:gap-8">
            <div className="min-w-0">
              <div className="stat-nums text-[11px] sm:text-xs text-muted">
                MY TEAM{rec(m.my_team) ? ` · ${rec(m.my_team)}` : ''}{fmtRank(m.my_team.rank) ? ` · ${fmtRank(m.my_team.rank)}` : ''}
              </div>
              <div className="font-display font-bold uppercase tracking-tight text-lg sm:text-3xl leading-[1.1] text-body mt-1 break-words">
                {m.my_team.team_name || 'My Team'}
              </div>
            </div>
            <div className="font-display font-semibold tracking-[0.16em] text-xs sm:text-sm text-faint whitespace-nowrap pt-4 sm:pt-0 sm:self-end sm:pb-1">
              WK {thisWeek.week}
            </div>
            <div className="min-w-0 text-right">
              <div className="stat-nums text-[11px] sm:text-xs text-muted">
                OPP{rec(m.opponent) ? ` · ${rec(m.opponent)}` : ''}{fmtRank(m.opponent.rank) ? ` · ${fmtRank(m.opponent.rank)}` : ''}
              </div>
              <div className="font-display font-bold uppercase tracking-tight text-lg sm:text-3xl leading-[1.1] text-muted mt-1 break-words">
                {m.opponent.team_name || 'Opponent'}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 sm:gap-8 mt-4">
            <div className="font-display font-bold text-3xl sm:text-5xl leading-none text-body">
              {(m.my_team.projected_score ?? 0).toFixed(1)}
            </div>
            <div className="text-center">
              <div className="font-display font-semibold tracking-[0.14em] text-[10px] sm:text-xs text-muted">PROJECTED</div>
              <div className="font-display font-bold text-xl sm:text-3xl leading-none text-accent-ink mt-1 whitespace-nowrap">
                {margin > 0 ? '+' : ''}{margin.toFixed(1)}
              </div>
            </div>
            <div className="font-display font-bold text-3xl sm:text-5xl leading-none text-muted text-right">
              {(m.opponent.projected_score ?? 0).toFixed(1)}
            </div>
          </div>

          {/* FIELD-POSITION BAR */}
          <div className="mt-4">
            <div
              className="relative h-8 rounded-sm border border-hairline overflow-hidden"
              style={{ background: 'var(--field)' }}
            >
              <div className="absolute inset-y-0 left-0 w-[10%]" style={{ background: 'var(--field-endzone)' }} />
              <div className="absolute inset-y-0 right-0 w-[10%]" style={{ background: 'var(--field-endzone-alt)' }} />
              {[20, 30, 40, 50, 60, 70, 80].map((x) => (
                <div key={x} className="absolute inset-y-0 w-px" style={{ left: `${x}%`, background: 'var(--field-line)' }} />
              ))}
              <div className="absolute inset-y-0 w-px" style={{ left: '50%', background: 'var(--line)' }} />
              <div
                className="absolute inset-y-0 w-0.5"
                style={{ left: `${markerPct}%`, background: 'var(--color-volt)' }}
              />
            </div>
            <div className="flex justify-between mt-1.5">
              <span className="stat-nums text-[10px] text-accent-ink">
                {m.favored === 'my_team' ? `◄ ${m.my_team.team_name || 'MY TEAM'} FAVORED BY ${Math.abs(margin).toFixed(1)}` : ''}
              </span>
              <span className="stat-nums text-[10px] text-faint">
                {m.favored === 'opponent' ? `${m.opponent.team_name || 'OPPONENT'} FAVORED BY ${Math.abs(margin).toFixed(1)} ►` : ''}
                {m.favored === 'even' ? 'EVEN MATCHUP' : ''}
              </span>
            </div>
            {/* Yahoo's own real server-computed win probability --
                no ESPN equivalent field, so this only ever renders
                for a Yahoo league. */}
            {m.win_probability != null && (
              <div className="text-center mt-1">
                <span className="stat-nums text-[10px] text-faint">
                  {Math.round(m.win_probability * 100)}% win probability (platform-computed)
                </span>
              </div>
            )}
          </div>
        </div>

        {/* OPTIMIZE ACTION */}
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 justify-between px-4 sm:px-6 py-4 border-t border-hairline bg-surface-2">
          {opt ? (
            <>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setShowOptimal((v) => !v)}
                  className="bg-volt text-volt-ink px-4 py-2 rounded-md hover:bg-volt-dark transition-colors flex items-center gap-2 focus:outline-none focus:ring-2 focus:ring-volt text-sm font-medium"
                >
                  <BoltIcon className="h-4 w-4" />
                  <span>{showOptimal ? 'Hide optimal lineup' : 'Optimize lineup'}</span>
                </button>
                <span className="stat-nums text-xs text-muted">
                  {opt.swaps.length > 0 ? (
                    <>Found <span className="text-accent-ink">{opt.swaps.length} upgrade{opt.swaps.length > 1 ? 's' : ''}</span> &mdash; projected <span className="text-accent-ink">+{opt.points_gained.toFixed(1)} pts</span> ({opt.current_projected.toFixed(1)} &rarr; {opt.optimized_projected.toFixed(1)})</>
                  ) : (
                    <>Your lineup is already the highest-projecting legal set ({opt.current_projected.toFixed(1)} pts).</>
                  )}
                </span>
              </div>
              <DataConfidenceBadge
                level="computed"
                label={thisWeek.projection_source ? 'Sleeper weekly proj' : `${thisWeek.league_info?.platform || 'ESPN'} weekly proj`}
              />
            </>
          ) : (
            // No optimizer button at all when there's nothing real to
            // toggle -- a disabled-looking action here would imply
            // one exists and just isn't ready, which isn't the case.
            <span className="stat-nums text-xs text-muted">
              {thisWeek.projection_note || 'Lineup optimization isn’t available for this platform.'}
            </span>
          )}
        </div>
        {opt && thisWeek.projection_source && thisWeek.projection_note && (
          <p className="stat-nums text-[11px] text-faint px-4 sm:px-6 pb-4 bg-surface-2 leading-relaxed">
            {thisWeek.projection_note}
          </p>
        )}
      </div>

      {/* BODY: lineup + rail */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_20rem] gap-6">
        <div className="bg-surface rounded-lg border border-hairline overflow-hidden">
          <div className="flex items-center gap-1 px-2 sm:px-3 pt-2">
            <button
              onClick={() => setLineupView('mine')}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                lineupView === 'mine' ? 'bg-volt text-volt-ink' : 'text-muted hover:text-body'
              }`}
            >
              My Lineup
            </button>
            <button
              onClick={() => setLineupView('matchup')}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                lineupView === 'matchup' ? 'bg-volt text-volt-ink' : 'text-muted hover:text-body'
              }`}
            >
              Matchup
            </button>
          </div>

          {lineupView === 'mine' ? (
            <>
              <div className="grid grid-cols-[3rem_1fr_auto] sm:grid-cols-[3.5rem_1fr_6rem_4rem_4rem] gap-2 px-3 py-2 border-b border-hairline stat-nums text-[10px] tracking-wider text-faint mt-2">
                <span>SLOT</span><span>PLAYER</span><span className="hidden sm:block">MATCHUP</span><span className="text-right">PROJ</span><span className="hidden sm:block text-right">ACT</span>
              </div>
              {starters.map((p) => renderRow(p, false))}
              {bench.length > 0 && (
                <>
                  <div className="stat-nums text-[10px] text-faint px-3 pt-3 pb-1 tracking-wider">BENCH</div>
                  {bench.map((p) => renderRow(p, true))}
                </>
              )}
              {ir.length > 0 && (
                <>
                  <div className="stat-nums text-[10px] text-faint px-3 pt-3 pb-1 tracking-wider">IR</div>
                  {ir.map((p) => renderRow(p, true))}
                </>
              )}
            </>
          ) : oppLineup.length === 0 ? (
            <div className="p-8 text-center">
              <p className="text-sm text-muted">Your opponent&apos;s lineup isn&apos;t available yet.</p>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-[1fr_2.25rem_1fr] items-center gap-1.5 px-2 sm:px-3 py-2 border-b border-hairline stat-nums text-[9px] tracking-wider text-faint mt-2">
                <span className="truncate">{m.my_team.team_name || 'MY TEAM'}</span>
                <span className="text-center">SLOT</span>
                <span className="truncate text-right">{m.opponent.team_name || 'OPPONENT'}</span>
              </div>
              {h2hStarterRows.map((row, i) => renderH2HRow(row, i))}
              {h2hBenchRows.length > 0 && (
                <>
                  <div className="stat-nums text-[10px] text-faint px-3 pt-3 pb-1 tracking-wider text-center">BENCH</div>
                  {h2hBenchRows.map((row, i) => renderH2HRow(row, i))}
                </>
              )}
            </>
          )}
        </div>

        {/* CALL RAIL */}
        <div className="space-y-3">
          <div className="font-display font-bold tracking-[0.1em] text-accent-ink">LINEUP CALL</div>
          <div className="yard-divider" />

          {opt && opt.swaps.length > 0 ? (
            opt.swaps.map((s, i) => (
              <div key={`swap-${i}`} className="border border-hairline bg-surface rounded-lg">
                <div className="px-4 py-2.5 border-b border-hairline flex items-center justify-between gap-2">
                  <span className="stat-nums text-[10px] tracking-wider text-muted">LINEUP UPGRADE</span>
                  <div className="flex items-center gap-1.5">
                    {confidenceBadge(s.confidence)}
                    <span className="stat-nums text-[10px] text-accent-ink">+{s.delta.toFixed(1)} PTS</span>
                  </div>
                </div>
                <div className="p-4">
                  <div className="text-sm font-medium text-body leading-snug">
                    Start <span className="text-accent-ink">{s.start_in.name}</span> over {s.bench_out.name}{s.slot ? ` at ${s.slot}` : ''}.
                  </div>
                  {s.confidence === 'risky' && (
                    <div className="stat-nums text-[11px] text-danger-700 mt-2 leading-relaxed">
                      {s.start_in.name} carries a live injury designation -- the point gap is real but the
                      floor on this projection is shakier than a healthy swap.
                    </div>
                  )}
                  <div className="stat-nums text-[11px] text-muted mt-2 leading-relaxed">
                    {s.start_in.name} projects {s.start_in.projected_points?.toFixed(1)} this week vs {s.bench_out.name}&apos;s {s.bench_out.projected_points?.toFixed(1)} &mdash; a {s.delta.toFixed(1)}-point swing on {thisWeek.projection_source ? 'Sleeper’s weekly projection, scored with your league’s rules' : `${thisWeek.league_info?.platform || 'ESPN'}’s own weekly projection`}.
                  </div>
                  <button
                    onClick={() => setShowOptimal(true)}
                    className="mt-3 stat-nums text-[11px] text-accent-ink hover:underline"
                  >
                    Show in lineup &#9656;
                  </button>
                </div>
              </div>
            ))
          ) : opt ? (
            <div className="border border-hairline bg-surface rounded-lg p-4">
              <div className="flex items-center gap-2">
                <CheckCircleIcon className="h-4 w-4 text-success-500" />
                <span className="text-sm font-medium text-body">Lineup is optimal</span>
              </div>
              <p className="stat-nums text-[11px] text-muted mt-2 leading-relaxed">
                No bench player out-projects a current starter at a slot they&apos;re eligible for.
              </p>
            </div>
          ) : (
            // opt === null: not a real "already optimal" result --
            // this platform (Yahoo today) has no real per-player
            // projection to optimize against at all. Distinct
            // message so this never reads as a false all-clear.
            <div className="border border-hairline bg-surface rounded-lg p-4">
              <div className="flex items-center gap-2">
                <InformationCircleIcon className="h-4 w-4 text-faint" />
                <span className="text-sm font-medium text-body">Optimizer not available</span>
              </div>
              <p className="stat-nums text-[11px] text-muted mt-2 leading-relaxed">
                {thisWeek.projection_note || 'This platform doesn’t expose real per-player weekly projections, so lineup optimization isn’t available.'}
              </p>
            </div>
          )}

          {(() => {
            // Starters in a real thin margin (< 1 pt) against their own
            // best bench option -- close enough that the optimizer's
            // 0.1pt threshold doesn't trigger a swap suggestion, but
            // not a confident call either. Already-flagged swaps get
            // their own full card above; skip those here.
            const closeCalls = (thisWeek.start_sit ?? []).filter(
              (c) => c.tier === 'toss_up' && !swapOutNames.has(c.name)
            )
            if (closeCalls.length === 0) return null
            return (
              <div className="border border-hairline bg-surface rounded-lg">
                <div className="px-4 py-2.5 border-b border-hairline">
                  <span className="stat-nums text-[10px] tracking-wider text-warning-700">CLOSE CALLS</span>
                </div>
                <div className="p-4 space-y-2">
                  {closeCalls.map((c, i) => (
                    <div key={`close-${i}`}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm text-body">
                          {c.name} <span className="text-xs text-muted">{c.position}</span>
                        </span>
                        {confidenceBadge(c.tier)}
                      </div>
                      {c.margin != null && (
                        <p className="stat-nums text-[11px] text-muted mt-1 leading-relaxed">
                          Only {c.margin > 0 ? '+' : ''}{c.margin.toFixed(1)} pts over {c.best_bench_alternative ?? 'the next best bench option'} at {c.slot} -- worth a look before kickoff.
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )
          })()}

          {thisWeek.starter_injuries && thisWeek.starter_injuries.length > 0 && (
            <div className="border border-hairline bg-surface rounded-lg">
              <div className="px-4 py-2.5 border-b border-hairline">
                <span className="stat-nums text-[10px] tracking-wider text-warning-700">STARTER STATUS</span>
              </div>
              <div className="p-4 space-y-2">
                {thisWeek.starter_injuries.map((inj, i) => (
                  <div key={`inj-${i}`} className="flex items-center justify-between">
                    <span className="text-sm text-body">{inj.name} <span className="text-xs text-muted">{inj.position}</span></span>
                    <span className={`stat-nums text-[10px] px-1.5 py-0.5 rounded font-medium ${getStatusColor(inj.status)}`}>
                      {formatStatusLabel(inj.status)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {waiverRecs && waiverRecs.recommendations.length > 0 && (
            <div className="border border-hairline bg-surface rounded-lg">
              <div className="px-4 py-2.5 border-b border-hairline flex items-center justify-between">
                <span className="stat-nums text-[10px] tracking-wider text-muted">{waiverRecs.watch_only ? 'WAIVER WATCH' : 'TOP WAIVER TARGET'}</span>
                <button onClick={() => setActiveTab('waiver')} className="stat-nums text-[10px] text-accent-ink hover:underline">All &#9656;</button>
              </div>
              {(() => {
                const top = waiverRecs.recommendations[0]
                const drop = top.drop_candidate
                const delta = top.value_delta
                const worthIt = delta == null ? null : delta > 0
                return (
                  <div className="p-4">
                    <div className="flex items-center gap-2">
                      <span className={`inline-flex items-center justify-center w-9 h-6 rounded text-[11px] font-semibold ${getPositionColor(top.player.position?.value)}`}>
                        {top.player.position?.value || '—'}
                      </span>
                      <span className="text-sm font-medium text-body">{top.player.name}</span>
                      {top.player.projected_points != null && (
                        <span className="stat-nums text-xs text-muted ml-auto">{top.player.projected_points.toFixed(0)} pts</span>
                      )}
                    </div>
                    {top.reason && (
                      <p className="stat-nums text-[11px] text-muted mt-2 leading-relaxed">{top.reason}</p>
                    )}
                    {drop && (
                      <div className={`mt-3 rounded-md border p-2.5 ${worthIt === false ? 'border-danger-200 bg-danger-50' : 'border-hairline bg-surface-2'}`}>
                        <p className="text-xs text-body">
                          Drop <span className="font-medium">{drop.name}</span>
                          {drop.position ? ` (${drop.position}${drop.position_matched ? '' : ', flex-eligible'})` : ''} to make room.
                        </p>
                        {delta != null && (
                          <p className={`stat-nums text-[11px] mt-1 ${worthIt ? 'text-success-700' : 'text-danger-700'}`}>
                            {top.kind === 'streamer'
                              ? `+${delta.toFixed(1)} pts to this week's lineup.`
                              : worthIt
                                ? `+${delta.toFixed(1)} projected season points for your team.`
                                : `Not a clear upgrade yet (${delta.toFixed(1)} pts).`}
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                )
              })()}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
