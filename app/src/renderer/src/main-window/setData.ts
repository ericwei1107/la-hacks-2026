import type { GameEvent, Recording, RoundSummary, SessionMeta } from '../services'

export function lastSummary(recording: Recording | undefined): RoundSummary | undefined {
  const summaries = recording?.roundSummaries ?? []
  return summaries.reduce<RoundSummary | undefined>(
    (latest, summary) => (!latest || summary.round >= latest.round ? summary : latest),
    undefined
  )
}

function family(key: string): string {
  return key.split(':')[0]
}

export function isExploited(situation: string | undefined, exploited: string[] | undefined): boolean {
  if (!situation || !exploited) return false
  return exploited.some(
    (key) => key === situation || (family(key) === family(situation) && (!key.includes(':') || !situation.includes(':')))
  )
}

export interface RoundScore {
  human: number
  bot: number
}

export function roundScore(session: SessionMeta): RoundScore {
  const human = session.rounds.filter((round) => round.winner === session.human_slot).length
  const bot = session.rounds.filter((round) => round.winner !== null && round.winner !== session.human_slot).length
  return { human, bot }
}

export interface ThrowCounts {
  broken: number
  total: number
}

export function throwCounts(events: GameEvent[], humanSlot: number): ThrowCounts {
  const broken = events.filter((event) => event.kind === 'throw_break' && event.actor === humanSlot).length
  const landed = events.filter((event) => event.kind === 'throw' && event.target === humanSlot).length
  return { broken, total: landed + broken }
}
