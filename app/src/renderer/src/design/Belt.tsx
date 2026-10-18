import { BELT_COLORS, beltFor, beltName, type BeltLevel } from './belts'

const LIGHT_OUTLINE = 'rgb(0 0 0 / 35%)'
const STRIPE_X: Record<1 | 2, number[]> = { 1: [53], 2: [50, 55] }

interface BeltProps {
  level: BeltLevel
  night?: boolean
  className?: string
}

export function Belt({ level, night = false, className }: BeltProps) {
  const fill = BELT_COLORS[level.rank]
  const stroke = night && level.rank === 'black' ? 'var(--color-overlay-text)' : LIGHT_OUTLINE
  return (
    <svg width="64" height="26" viewBox="0 0 64 26" className={className} aria-hidden="true">
      <rect x="0.5" y="7.5" width="63" height="9" rx="2" fill={fill} stroke={stroke} />
      {level.stripes > 0 &&
        STRIPE_X[level.stripes as 1 | 2].map((x) => <rect key={x} x={x} y="8" width="3" height="8" fill="#1D1B16" />)}
      <path d="M28 15 L23 25 L28.5 25 L31 17 Z" fill={fill} stroke={stroke} strokeLinejoin="round" />
      <path d="M36 15 L41 25 L35.5 25 L33 17 Z" fill={fill} stroke={stroke} strokeLinejoin="round" />
      <rect x="26.5" y="4.5" width="11" height="14" rx="3" fill={fill} stroke={stroke} />
    </svg>
  )
}

interface BeltSquaresProps {
  rounds: { round: number; mastery?: number; fixed?: boolean }[]
}

export function BeltSquares({ rounds }: BeltSquaresProps) {
  const levels = rounds.map((round) => ({ round: round.round, level: beltFor(round.mastery, round.fixed) }))
  const description = levels.map(({ round, level }) => `Round ${round}: ${beltName(level)}`).join(', ')
  return (
    <div className="flex gap-1" role="img" aria-label={description}>
      {levels.map(({ round, level }) => (
        <div
          key={round}
          title={`Round ${round}: ${beltName(level)}`}
          className={`size-4 shrink-0 rounded-[3px] ${level.rank === 'white' ? 'border border-[#1D1B164D]' : ''}`}
          style={{ backgroundColor: BELT_COLORS[level.rank] }}
        />
      ))}
    </div>
  )
}
