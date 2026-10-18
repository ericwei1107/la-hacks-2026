export type BeltRank = 'white' | 'yellow' | 'orange' | 'green' | 'blue' | 'brown' | 'black'

export interface BeltLevel {
  rank: BeltRank
  stripes: 0 | 1 | 2
}

const BANDS: { rank: BeltRank; from: number; to: number }[] = [
  { rank: 'yellow', from: 0.15, to: 0.3 },
  { rank: 'orange', from: 0.3, to: 0.45 },
  { rank: 'green', from: 0.45, to: 0.6 },
  { rank: 'blue', from: 0.6, to: 0.75 },
  { rank: 'brown', from: 0.75, to: 0.85 }
]

export const BELT_COLORS: Record<BeltRank, string> = {
  white: 'var(--color-belt-white)',
  yellow: 'var(--color-belt-yellow)',
  orange: 'var(--color-belt-orange)',
  green: 'var(--color-belt-green)',
  blue: 'var(--color-belt-blue)',
  brown: 'var(--color-belt-brown)',
  black: 'var(--color-belt-black)'
}

function stripesThrough(mastery: number, from: number, to: number): 0 | 1 | 2 {
  const progress = Math.min(1, (mastery - from) / (to - from))
  return Math.min(2, Math.floor(progress * 3)) as 0 | 1 | 2
}

export function beltFor(mastery: number | undefined, fixed: boolean | undefined): BeltLevel {
  if (fixed) return { rank: 'black', stripes: 0 }
  const value = mastery ?? 0
  if (value < 0.15) return { rank: 'white', stripes: 0 }
  const band = [...BANDS].reverse().find((candidate) => value >= candidate.from) ?? BANDS[0]
  return { rank: band.rank, stripes: stripesThrough(value, band.from, band.to) }
}

export function beltName({ rank, stripes }: BeltLevel): string {
  const name = `${rank[0].toUpperCase()}${rank.slice(1)} belt`
  if (stripes === 0) return name
  return `${name}, ${stripes} stripe${stripes === 1 ? '' : 's'}`
}
