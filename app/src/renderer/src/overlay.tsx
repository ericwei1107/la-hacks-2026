import { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { useQueryClient } from '@tanstack/react-query'
import { Belt, beltFor, beltName, characterName, habitName, NOTATION_TOKEN } from './design'
import { useConfig, useEventListener, useLearning, useLatestCoach, useLatestPlan, useLatestSummary, useLiveState, useSummaryListener, type CoachMessage, type LearningRound, type RoundSummary } from './services'
import './fonts'
import './styles.css'
import { ServicesProvider } from './services'

const ROUND_LIVE_MS = 2_000
const COUNTDOWN_MS = 10_000

interface Card {
  sessionId: string
  round: number
  openedAt: number
  matchOver: boolean
}

function notationText(text: string) {
  const parts: React.ReactNode[] = []
  let offset = 0
  for (const match of text.matchAll(NOTATION_TOKEN)) {
    const index = match.index ?? 0
    if (index > offset) parts.push(text.slice(offset, index))
    parts.push(<span key={`${index}-${match[0]}`} className="font-mono">{match[0]}</span>)
    offset = index + match[0].length
  }
  if (offset < text.length) parts.push(text.slice(offset))
  return parts
}

function Habits({ sessionId, round, exploited }: { sessionId: string; round: LearningRound | undefined; exploited: string[] }) {
  const entries = useMemo(() => Object.entries(round?.habits ?? {}).map(([key, habit]) => ({
    key,
    habit,
    target: exploited.includes(key) || exploited.some((item) => item.split(':')[0] === key.split(':')[0] && (!item.includes(':') || !key.includes(':')))
  })).sort((a, b) => Number(b.target) - Number(a.target) || (a.habit.mastery ?? 0) - (b.habit.mastery ?? 0)), [round, exploited])

  if (!round) {
    return <p className="px-4 py-3 text-sm leading-5 text-overlay-muted">Learning your habits. Belts show up after round 1.</p>
  }

  return (
    <div className="flex flex-col">
      {entries.map(({ key, habit, target }) => {
        const level = beltFor(habit.mastery, habit.fixed)
        return (
          <div key={`${sessionId}-${key}`} className="flex min-h-[44px] items-center gap-2 px-3" style={{ backgroundColor: target ? 'rgb(181 70 43 / 10%)' : undefined }}>
            <Belt level={level} night className="shrink-0" />
            <div className="flex min-w-0 grow flex-col">
              <span className="truncate text-sm leading-[18px] font-bold text-overlay-text">{habitName(key)}</span>
              <span className="text-xs leading-4 text-overlay-muted">{beltName(level)}</span>
            </div>
            {target && <span className="shrink-0 rounded-sm bg-bot px-2 py-1 text-[10px] leading-3 font-bold text-overlay-text">Bot&apos;s target</span>}
            {habit.fixed && <span className="shrink-0 rounded-sm border border-solid border-overlay-text px-2 py-1 text-[10px] leading-3 font-bold text-overlay-text">Fixed</span>}
            <span className="w-10 shrink-0 text-right font-mono text-sm text-overlay-text">{Math.round((habit.mastery ?? 0) * 100)}%</span>
          </div>
        )
      })}
    </div>
  )
}

function BetweenRounds({ card, coach, summary, botCharacter }: {
  card: Card
  coach: CoachMessage | null
  summary: RoundSummary | null
  botCharacter: string
}) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 100)
    return () => window.clearInterval(timer)
  }, [])
  const remaining = Math.max(0, card.openedAt + COUNTDOWN_MS - now)
  const seconds = Math.ceil(remaining / 1000)
  const result = !summary
    ? `Round ${card.round}`
    : summary.winner === null
      ? `Round ${card.round} is a draw`
      : summary.winner === summary.human_slot
        ? `Round ${card.round} goes to you`
        : `Round ${card.round} goes to ${botCharacter}`
  return (
    <section className="mat-card absolute bottom-16 left-1/2 flex min-h-[250px] w-[1000px] -translate-x-1/2 items-stretch overflow-hidden rounded-sm text-text shadow-2xl">
      <div className="flex grow flex-col justify-center gap-5 px-10 py-8">
        <p className="text-base font-bold text-text-muted">{result}</p>
        {coach
          ? <p className="text-[30px] leading-[40px] font-bold text-text">{coach.text}</p>
          : <p className="text-[30px] leading-[40px] text-text-muted">Coach is reviewing the round…</p>}
      </div>
      <div className="flex w-[200px] shrink-0 flex-col items-center justify-center gap-1 border-l border-solid border-[#1D1B1626]">
        {card.matchOver
          ? <span className="font-display text-xl leading-7 text-primary">Set over</span>
          : <>
            <span className="font-display text-[64px] leading-[72px] text-primary">{seconds}</span>
            <span className="text-base font-bold text-text">Round {card.round + 1}</span>
          </>}
      </div>
      {!card.matchOver && (
        <div className="absolute right-0 bottom-0 left-0 h-3 bg-track">
          <div className="h-full bg-primary" style={{ width: `${(remaining / COUNTDOWN_MS) * 100}%` }} />
        </div>
      )}
    </section>
  )
}

function OverlayContent() {
  const state = useLiveState()
  const plan = useLatestPlan()
  const coach = useLatestCoach()
  const summary = useLatestSummary()
  const config = useConfig()
  const client = useQueryClient()
  useSummaryListener((record) => {
    if (record.session_id === state?.record.session_id) {
      void client.invalidateQueries({ queryKey: ['analytics', 'learning', record.session_id] })
    }
  })
  const sessionId = state?.record.session_id
  const learning = useLearning(sessionId ?? '')
  const [now, setNow] = useState(Date.now())
  const [card, setCard] = useState<Card | null>(null)

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 250)
    return () => window.clearInterval(timer)
  }, [])

  useEventListener((event) => {
    if (event.kind === 'round_end' && event.session_id === sessionId) {
      setCard({ sessionId: event.session_id, round: event.round, openedAt: Date.now(), matchOver: event.detail?.match_over === true })
    } else if (event.kind === 'round_start') {
      setCard((current) => current?.sessionId === event.session_id ? null : current)
    }
  })

  const isLive = Boolean(state && now - state.receivedAt < ROUND_LIVE_MS)
  const cardClosed = card !== null && (!isLive || !state || state.record.session_id !== card.sessionId || state.record.round > card.round)

  useEffect(() => {
    if (cardClosed) setCard(null)
  }, [cardClosed])

  const openCard = card && !cardClosed ? card : null
  const livePlan = plan?.record.session_id === sessionId ? plan : null
  const activeSummary = summary && summary.record.session_id === sessionId ? summary.record : null
  const cardCoach = openCard && coach?.record.session_id === openCard.sessionId && coach.record.round === openCard.round ? coach.record : null
  const cardSummary = openCard && activeSummary?.session_id === openCard.sessionId && activeSummary.round === openCard.round ? activeSummary : null
  const learningRounds = [...(learning.data?.rounds ?? [])].sort((a, b) => a.round - b.round)
  const lastRound = learningRounds[learningRounds.length - 1]
  const showingCard = openCard !== null

  return (
    <div className="relative h-[1080px] w-[1920px] overflow-hidden bg-transparent">
      {isLive && sessionId && !showingCard && (
        <section className="absolute top-[136px] left-12 w-hud overflow-hidden border-t-4 border-solid border-overlay-line bg-overlay/[0.90] text-overlay-text">
          <header className="flex items-baseline justify-between px-4 pt-3 pb-2">
            <h1 className="font-display text-xl leading-7">{characterName(config.data?.bot_character)}</h1>
            <span className="font-mono text-sm text-overlay-muted">Level {config.data?.difficulty ?? '—'}</span>
          </header>
          {livePlan && <div className="border-t border-solid border-[#FFFFFF1A] px-4 py-2 text-sm leading-5"><span className="mr-2 font-bold">Plan:</span>{notationText(livePlan.record.note)}</div>}
          <div className="border-t border-solid border-[#FFFFFF1A]">
            <Habits sessionId={sessionId} round={lastRound} exploited={activeSummary?.exploited ?? []} />
          </div>
        </section>
      )}
      {openCard && <BetweenRounds
        card={openCard}
        coach={cardCoach}
        summary={cardSummary}
        botCharacter={characterName(config.data?.bot_character)}
      />}
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <ServicesProvider>
    <OverlayContent />
  </ServicesProvider>
)
