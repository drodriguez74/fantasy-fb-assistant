// Chart data type definitions for Fantasy Football Analytics

export interface PlayerComparisonData {
  player: string
  projectedPoints: number
  consistency: number
  ceiling: number
  floor: number
  targetShare: number
  snapCount: number
  riskScore: number
  valueScore: number
  upsideRating: number
  opportunityShare: number
}

export interface TrendData {
  week: number
  points: number
  player: string
  projection?: number
}

export interface ScheduleDifficultyData {
  week: number
  opponent: string
  difficulty: number
  rating: 'EASY' | 'MODERATE' | 'DIFFICULT'
  player: string
}

export interface BreakoutCandidateData {
  player: string
  probability: number
  age: number
  ownership: number
  targetShare: number
  snapCount: number
  efficiency: number
}

export interface SituationalData {
  situation: string
  home: number
  away: number
  player: string
}

/*
 * Chart colors are theme-aware and live in src/index.css as design tokens
 * (--viz-1..8 categorical palette + --viz-pos/-warn/-neg semantic scale,
 * with distinct light and dark values). Read them at runtime via the
 * `useChartColors()` hook in src/hooks/useChartColors.ts — Recharts needs
 * resolved color strings, and hardcoded hex here never responded to dark mode.
 */
