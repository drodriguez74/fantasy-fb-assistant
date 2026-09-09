import { useState } from 'react'
import clsx from 'clsx'
import { getPositionColor } from './playerDisplay'

// ESPN's public image CDNs. Headshots exist for most skill players; team
// logos cover D/ST and act as the corner badge. Both 404 cleanly for
// unknowns, so every <img> has an onError fallback.
const headshotUrl = (id?: number | string | null) =>
  id ? `https://a.espncdn.com/i/headshots/nfl/players/full/${id}.png` : null

const teamLogoUrl = (abbr?: string | null) => {
  if (!abbr) return null
  const a = abbr.toLowerCase()
  if (a === 'fa' || a === 'none' || a === '') return null
  return `https://a.espncdn.com/i/teamlogos/nfl/500/${a}.png`
}

interface Props {
  playerId?: number | string | null
  name: string
  position?: string
  team?: string | null
  size?: number
  className?: string
}

/** Round player headshot with a team-logo corner badge; falls back to a
 *  position-tinted monogram when no image is available (rookies, K, D/ST). */
export function PlayerAvatar({ playerId, name, position, team, size = 34, className }: Props) {
  const [headFailed, setHeadFailed] = useState(false)
  const [logoFailed, setLogoFailed] = useState(false)

  const pos = (position || '').toUpperCase()
  const isDST = pos === 'DEF' || pos === 'D/ST' || pos === 'DST'
  const logo = teamLogoUrl(team)
  const head = isDST ? logo : headshotUrl(playerId)

  const monogram = name
    .split(/\s+/)
    .map((w) => w[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase()

  return (
    <span
      className={clsx(
        'relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full border border-hairline bg-surface-2',
        className,
      )}
      style={{ width: size, height: size }}
    >
      {head && !headFailed ? (
        <img
          src={head}
          alt=""
          loading="lazy"
          onError={() => setHeadFailed(true)}
          className={clsx('h-full w-full', isDST ? 'object-contain p-1' : 'object-cover')}
        />
      ) : (
        <span
          className={clsx(
            'flex h-full w-full items-center justify-center rounded-full text-[11px] font-bold',
            getPositionColor(pos),
          )}
        >
          {monogram || '?'}
        </span>
      )}

      {!isDST && logo && !logoFailed && (
        <img
          src={logo}
          alt=""
          loading="lazy"
          onError={() => setLogoFailed(true)}
          className="absolute -bottom-px -right-px h-3.5 w-3.5 rounded-full bg-page object-contain ring-1 ring-page"
        />
      )}
    </span>
  )
}
