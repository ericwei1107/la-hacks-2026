import { ArrowRight, Button, characterName, duration, EmptyState, score, setTime, setTimeInSentence, Skeleton } from '../../design'
import { useRecording, useServiceStatus, type GameEvent, type Recording, type SessionMeta } from '../../services'
import { useFrame } from '../frame'
import { ScreenBanner, Screen, useOfflineService } from '../Screen'
import { isExploited, roundScore, throwCounts } from '../setData'

const TIMELINE_WIDTH = 472
const TIMELINE_LENGTH = 452

function resultWord(session: SessionMeta): { word: 'Win' | 'Loss' | 'Draw'; text: string } {
  const { human, bot } = roundScore(session)
  const word = human > bot ? 'Win' : bot > human ? 'Loss' : 'Draw'
  return { word, text: score(human, bot) }
}

function SetCard({ session, selected, onSelect }: { session: SessionMeta; selected: boolean; onSelect: () => void }) {
  const { word, text } = resultWord(session)
  const length = session.ended_at ? duration(session.started_at, session.ended_at) : 'in progress'
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
      className={`focus-ring flex items-center gap-4 px-[20px] py-4 text-left ${
        selected ? 'rounded-md border-2 border-solid border-primary bg-surface' : 'border-2 border-b border-solid border-[#1D1B1626]'
      }`}
    >
      <span className="flex grow basis-0 flex-col gap-[2px]">
        <span className="text-sm leading-[18px] font-medium text-text-muted">{setTime(session.started_at)}</span>
        <span className="text-lg/lg font-bold text-text">
          {characterName(session.human_character)} vs {characterName(session.bot_character)}
        </span>
        <span className="text-base/sm text-text-muted">
          Level {session.difficulty} · {session.rounds.length} {session.rounds.length === 1 ? 'round' : 'rounds'} · {length}
        </span>
      </span>
      <span className="flex w-[84px] shrink-0 flex-col items-end">
        <span className={`text-sm leading-[18px] font-bold ${word === 'Win' ? 'text-primary-text' : 'text-text-muted'}`}>{word}</span>
        <span className="text-xl leading-[34px] font-[900] text-text">{text}</span>
      </span>
    </button>
  )
}

type MarkerShape = 'dot' | 'square' | 'diamond' | 'triangle'

const SHAPES: Partial<Record<GameEvent['kind'], MarkerShape>> = {
  hit: 'dot',
  counter_hit: 'dot',
  block: 'square',
  throw: 'diamond',
  throw_break: 'diamond',
  knockdown: 'triangle'
}

function Marker({ shape, x, above, color }: { shape: MarkerShape; x: number; above: boolean; color: string }) {
  const y = above ? 18 : 54
  if (shape === 'dot') return <circle cx={x} cy={y} r="5" fill={color} />
  if (shape === 'square') {
    return <rect x={x - 5} y={y - 5} width="10" height="10" fill="var(--color-surface)" stroke={color} strokeWidth="2" />
  }
  if (shape === 'diamond') return <path d={`M${x} ${y - 7}L${x + 7} ${y}L${x} ${y + 7}L${x - 7} ${y}Z`} fill={color} />
  const d = above ? `M${x - 7} ${y - 8}L${x + 7} ${y - 8}L${x} ${y + 7}Z` : `M${x - 7} ${y + 8}L${x + 7} ${y + 8}L${x} ${y - 7}Z`
  return <path d={d} fill={color} />
}

function LegendItem({ shape, label }: { shape: MarkerShape; label: string }) {
  return (
    <span className="flex items-center gap-[6px] text-sm leading-[18px] text-text">
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
        {shape === 'dot' && <circle cx="6" cy="6" r="5" fill="var(--color-text)" />}
        {shape === 'square' && <rect x="1" y="1" width="10" height="10" fill="none" stroke="var(--color-text)" strokeWidth="2" />}
        {shape === 'diamond' && <path d="M6 0L12 6L6 12L0 6Z" fill="var(--color-text)" />}
        {shape === 'triangle' && <path d="M0 1L12 1L6 11Z" fill="var(--color-text)" />}
      </svg>
      {label}
    </span>
  )
}

function roundLength(session: SessionMeta, events: GameEvent[], round: number): number {
  const meta = session.rounds.find((candidate) => candidate.round === round)
  const lastEvent = events.filter((event) => event.round === round).reduce((max, event) => Math.max(max, event.frame), 0)
  return Math.max(meta?.end_frame ?? 0, lastEvent, 1)
}

function Timeline({ session, recording }: { session: SessionMeta; recording: Recording }) {
  const rounds = session.rounds.map((round) => round.round)
  const lengths = rounds.map((round) => roundLength(session, recording.events, round))
  const scale = TIMELINE_LENGTH / Math.max(...lengths, 1)
  const bot = characterName(session.bot_character)
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-4">
        <div className="w-[84px] shrink-0" />
        <span className="text-sm leading-[18px] text-text-muted">Above the line: you, in indigo. Below: {bot}.</span>
      </div>
      {session.rounds.map((round, index) => {
        const summary = recording.roundSummaries.find((candidate) => candidate.round === round.round)
        const end = lengths[index] * scale
        const won = round.winner === session.human_slot
        const label = round.winner === null ? 'Draw' : won ? 'You win' : `${bot} wins`
        return (
          <div key={round.round} className={`flex items-center gap-4 ${index > 0 ? 'border-t border-solid border-t-[#1D1B1614]' : ''}`}>
            <div className="flex w-[84px] shrink-0 flex-col">
              <span className="text-lg leading-[26px] font-[900] text-text">R{round.round}</span>
              <span className={`text-sm leading-[18px] font-bold ${won ? 'text-primary-text' : 'text-text-muted'}`}>{label}</span>
            </div>
            <svg width={TIMELINE_WIDTH} height="72" viewBox={`0 0 ${TIMELINE_WIDTH} 72`} className="shrink-0" role="img" aria-label={`Round ${round.round} events`}>
              <path d={`M0 36H${end}`} fill="none" stroke="#1D1B1659" strokeWidth="1.5" />
              <path d={`M${end} 28V44`} fill="none" stroke="#1D1B1680" strokeWidth="1.5" />
              {recording.events
                .filter((event) => event.round === round.round && SHAPES[event.kind] && event.actor !== undefined)
                .map((event, eventIndex) => {
                  const above = event.actor === session.human_slot
                  const color = above
                    ? 'var(--color-primary)'
                    : isExploited(event.situation, summary?.exploited)
                      ? 'var(--color-bot)'
                      : 'var(--color-text-muted)'
                  const x = Math.min(Math.max(event.frame * scale, 7), end)
                  return <Marker key={eventIndex} shape={SHAPES[event.kind]!} x={x} above={above} color={color} />
                })}
            </svg>
          </div>
        )
      })}
    </div>
  )
}

function Totals({ session, recording }: { session: SessionMeta; recording: Recording }) {
  const dealt = recording.roundSummaries.reduce((sum, summary) => sum + summary.bot_damage_taken, 0)
  const taken = recording.roundSummaries.reduce((sum, summary) => sum + summary.human_damage_taken, 0)
  const knockdowns = recording.events.filter((event) => event.kind === 'knockdown')
  const yours = knockdowns.filter((event) => event.actor === session.human_slot).length
  const theirs = knockdowns.filter((event) => event.actor !== undefined && event.actor !== session.human_slot).length
  const throws = throwCounts(recording.events, session.human_slot)
  const items = [
    [String(dealt), 'Damage dealt'],
    [String(taken), 'Damage taken'],
    [score(yours, theirs), 'Knockdowns'],
    [`${throws.broken} of ${throws.total}`, 'Throws broken']
  ]
  return (
    <div className="flex gap-6 border-t border-solid border-t-[#1D1B161F] pt-[20px]">
      {items.map(([value, label]) => (
        <div key={label} className="flex grow basis-0 flex-col gap-[2px]">
          <span className="text-xl leading-[34px] font-[900] text-text">{value}</span>
          <span className="text-sm leading-[18px] text-text-muted">{label}</span>
        </div>
      ))}
    </div>
  )
}

function SetDetail({ session }: { session: SessionMeta }) {
  const { open } = useFrame()
  const recording = useRecording(session.session_id)
  const { human, bot } = roundScore(session)
  const botName = characterName(session.bot_character)
  const result = human > bot ? `Win ${score(human, bot)} over ${botName}` : bot > human ? `Loss ${score(human, bot)} to ${botName}` : `Draw ${score(human, bot)} with ${botName}`
  return (
    <section className="flex grow basis-0 flex-col gap-[20px] rounded-md border border-solid border-[#1D1B1626] bg-surface px-[28px] pt-6 pb-[28px]">
      <div className="flex items-end justify-between gap-4">
        <div className="flex flex-col gap-1">
          <span className="text-base/sm font-medium text-text-muted">
            {setTimeInSentence(session.started_at)}, level {session.difficulty}
          </span>
          <h2 className="font-display text-xl leading-[36px] tracking-tight text-text">{result}</h2>
        </div>
        <Button onClick={() => open('replay', { sessionId: session.session_id })}>
          Replay analysis
          <ArrowRight />
        </Button>
      </div>
      <div className="flex items-center gap-4 border-y border-solid border-y-[#1D1B161F] py-3">
        <LegendItem shape="dot" label="Hit" />
        <LegendItem shape="square" label="Block" />
        <LegendItem shape="diamond" label="Throw" />
        <LegendItem shape="triangle" label="Knockdown" />
        <span className="grow basis-0" />
        <span className="flex items-center gap-[6px] text-sm leading-[18px] text-text">
          <span className="size-[10px] shrink-0 rounded-[1px] bg-bot" />
          Bot's planned exploit
        </span>
      </div>
      {recording.isPending && (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-[72px] w-full" />
          <Skeleton className="h-[72px] w-full" />
        </div>
      )}
      {recording.isError && <p className="text-base/base text-text-muted">This set's recording isn't available.</p>}
      {recording.data && (
        <>
          <Timeline session={session} recording={recording.data} />
          <Totals session={session} recording={recording.data} />
        </>
      )}
    </section>
  )
}

function SessionsSkeleton() {
  return (
    <div className="flex grow basis-0 items-start gap-12">
      <div className="flex w-[380px] shrink-0 flex-col gap-1">
        {[0, 1, 2, 3].map((key) => (
          <Skeleton key={key} className="h-[104px] w-full rounded-md" faint={key > 0} />
        ))}
      </div>
      <Skeleton className="h-[540px] grow basis-0 rounded-md" faint />
    </div>
  )
}

export function Sessions() {
  const { sessions, sessionsFailed, selectedId, select } = useFrame()
  const brain = useServiceStatus('brain')
  const offline = useOfflineService(['brain'])
  const selected = sessions?.find((session) => session.session_id === selectedId)

  return (
    <Screen title="Sessions">
      <ScreenBanner service={offline} line="Your sets show up again when it reconnects." />
      {!sessions && !sessionsFailed && <SessionsSkeleton />}
      {sessions && sessions.length === 0 && (
        <EmptyState
          headline="The mat is empty."
          line="Play a set against Kumite and it shows up here."
          status={
            brain.state === 'online'
              ? { online: true, text: 'The brain is connected and waiting for round 1.' }
              : { online: false, text: 'The brain is offline. Start it and your sets show up here.' }
          }
        />
      )}
      {sessions && sessions.length > 0 && (
        <div className="flex grow basis-0 items-start gap-12">
          <div className="flex w-[380px] shrink-0 flex-col gap-1">
            {sessions.map((session) => (
              <SetCard
                key={session.session_id}
                session={session}
                selected={session.session_id === selectedId}
                onSelect={() => select(session.session_id)}
              />
            ))}
          </div>
          {selected && <SetDetail session={selected} />}
        </div>
      )}
    </Screen>
  )
}
