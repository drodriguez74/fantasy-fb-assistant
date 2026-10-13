// A long list shown `limit` at a time, with a count of what's hidden. Only the
// visible rows are rendered, so a 230-row list costs 10 rows until opened.
import { useState, type ReactNode } from 'react'

export function ShowMore<T>({
  items,
  limit,
  render,
  className = '',
  noun = 'more',
  as: Wrapper = 'ul',
}: {
  items: T[]
  limit: number
  render: (item: T, index: number) => ReactNode
  className?: string
  noun?: string
  as?: 'ul' | 'div'
}) {
  const [all, setAll] = useState(false)
  const shown = all ? items : items.slice(0, limit)
  const hidden = items.length - shown.length
  return (
    <>
      <Wrapper className={className}>{shown.map(render)}</Wrapper>
      {(hidden > 0 || (all && items.length > limit)) && (
        <button onClick={() => setAll(!all)} className="mt-1 text-xs text-muted underline hover:text-body">
          {all ? 'Show fewer' : `Show ${hidden} ${noun}`}
        </button>
      )}
    </>
  )
}
