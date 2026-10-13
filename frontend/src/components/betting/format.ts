// One number format for the whole Bets page (2026-10-12 review: the same pick
// read 72% in one place and 72.4% in another). Chances are whole percents
// except under 10%, where the decimal matters (a 6-pick at 3.4%); edges are
// signed with one decimal; rates in record tables (ROI, hit rate) one decimal.

/** A chance to win / hit: "72%", "3.4%". */
export const chance = (p: number | null | undefined) => {
  if (p == null) return '—'
  const v = p * 100
  return v > 0 && v < 10 ? `${v.toFixed(1)}%` : `${Math.round(v)}%`
}

/** A rate in a record table (ROI, calibration): "12.3%". */
export const rate = (p: number | null | undefined) => (p == null ? '—' : `${(p * 100).toFixed(1)}%`)

/** An edge / expected value: "+3.2%". */
export const signedPct = (x: number) => `${x > 0 ? '+' : ''}${(x * 100).toFixed(1)}%`

/** A signed number: units won, "+1.25". */
export const signedNum = (n: number, digits = 2) => `${n > 0 ? '+' : ''}${n.toFixed(digits)}`

/** American odds: "+135", "-110". */
export const odds = (o: number | null | undefined) => (o == null ? '—' : o > 0 ? `+${o}` : `${o}`)

/** Dollars: "$12.50", "-$3.00". */
export const money = (x: number) => `${x < 0 ? '-' : ''}$${Math.abs(x).toFixed(2)}`
