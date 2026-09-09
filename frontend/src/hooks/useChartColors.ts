import { useEffect, useState } from 'react'

/**
 * Resolved colors for Recharts (and any other lib that needs real color
 * values rather than Tailwind classes).
 *
 * Recharts renders SVG with literal `fill`/`stroke` strings, so it can't
 * consume `var(--x)` utilities the way the rest of the app does. This hook
 * reads the design tokens off `<html>` at runtime and re-reads them whenever
 * the theme flips (the `data-theme` attribute — see hooks/useTheme.tsx — or an
 * OS `prefers-color-scheme` change while no explicit choice is set).
 *
 * Token source of truth: src/index.css.
 *   axis / grid / ticks -> the hairline + muted/faint text tokens
 *   series              -> the --viz-1..8 categorical palette (light + dark)
 *   pos / warn / neg     -> the --viz semantic good/caution/bad scale
 */
export interface ChartColors {
  /** card/tooltip background */
  surface: string
  /** primary text on `surface` */
  text: string
  /** axis labels, legend text */
  textMuted: string
  /** secondary ticks (e.g. radius axis) */
  textFaint: string
  /** CartesianGrid / PolarGrid stroke */
  grid: string
  /** axis line stroke */
  axis: string
  /** 8-hue categorical palette, readable on both --surface values */
  series: string[]
  /** semantic good / caution / bad (risk tiers, deltas) */
  pos: string
  warn: string
  neg: string
}

function readChartColors(): ChartColors {
  const fallback: ChartColors = {
    surface: '#ffffff',
    text: '#16160f',
    textMuted: '#6c6c64',
    textFaint: '#9c9c93',
    grid: '#e4e4de',
    axis: '#d6d6cf',
    series: ['#2563eb', '#0f9d58', '#d97706', '#dc2626', '#0891b2', '#7c3aed', '#db2777', '#b45309'],
    pos: '#0f9d58',
    warn: '#d97706',
    neg: '#dc2626',
  }

  if (typeof window === 'undefined') return fallback

  const s = getComputedStyle(document.documentElement)
  const v = (name: string, dflt: string) => s.getPropertyValue(name).trim() || dflt

  return {
    surface: v('--surface', fallback.surface),
    text: v('--text', fallback.text),
    textMuted: v('--text-muted', fallback.textMuted),
    textFaint: v('--text-faint', fallback.textFaint),
    grid: v('--hairline', fallback.grid),
    axis: v('--line', fallback.axis),
    series: fallback.series.map((d, i) => v(`--viz-${i + 1}`, d)),
    pos: v('--viz-pos', fallback.pos),
    warn: v('--viz-warn', fallback.warn),
    neg: v('--viz-neg', fallback.neg),
  }
}

export function useChartColors(): ChartColors {
  const [colors, setColors] = useState<ChartColors>(readChartColors)

  useEffect(() => {
    const update = () => setColors(readChartColors())
    update()

    const observer = new MutationObserver(update)
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    })

    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    mq.addEventListener('change', update)

    return () => {
      observer.disconnect()
      mq.removeEventListener('change', update)
    }
  }, [])

  return colors
}

/** Pick a stable series color by index (wraps at 8). */
export function seriesColor(colors: ChartColors, index: number): string {
  return colors.series[index % colors.series.length]
}

/** Map a 0..1 probability to the semantic good/caution/bad scale. */
export function probabilityColor(colors: ChartColors, probability: number): string {
  if (probability >= 0.7) return colors.pos
  if (probability >= 0.5) return colors.warn
  return colors.neg
}
