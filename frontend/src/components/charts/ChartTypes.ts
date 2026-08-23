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

interface ChartColors {
  primary: string
  secondary: string
  success: string
  warning: string
  danger: string
  info: string
  light: string
  dark: string
}

export const CHART_COLORS: ChartColors = {
  primary: '#3B82F6',    // Blue
  secondary: '#6B7280',  // Gray
  success: '#10B981',    // Green
  warning: '#F59E0B',    // Yellow
  danger: '#EF4444',     // Red
  info: '#06B6D4',       // Cyan
  light: '#F3F4F6',      // Light Gray
  dark: '#1F2937'        // Dark Gray
}

export const RISK_COLORS = {
  LOW: '#10B981',       // Green
  MEDIUM: '#F59E0B',    // Yellow
  HIGH: '#EF4444'       // Red
}
