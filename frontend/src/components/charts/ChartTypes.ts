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

export interface HeatmapData {
  x: string
  y: string
  value: number
  label?: string
}

export interface ChartColors {
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

export const POSITION_COLORS = {
  QB: '#8B5CF6',   // Purple
  RB: '#F59E0B',   // Orange
  WR: '#10B981',   // Green
  TE: '#EF4444',   // Red
  K: '#6B7280',    // Gray
  DEF: '#1F2937'   // Dark
}

export const DIFFICULTY_COLORS = {
  EASY: '#10B981',      // Green
  MODERATE: '#F59E0B',  // Yellow
  DIFFICULT: '#EF4444'  // Red
}

export const RISK_COLORS = {
  LOW: '#10B981',       // Green
  MEDIUM: '#F59E0B',    // Yellow
  HIGH: '#EF4444'       // Red
}