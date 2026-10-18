import { Belt, BeltSquares, beltFor, beltName, EmptyState, habitName, habitShort, Meter, optionName, Skeleton } from '../../design'
import { useLearning, useRecording, type LearningMetrics, type LearningRound } from '../../services'
import { SavingNote, useFrame, useSavingRound } from '../frame'
import { Screen, ScreenBanner, useOfflineService } from '../Screen'
import { isExploited, lastSummary } from '../setData'

const CHART_LEFT = 44
const CHART_RIGHT = 584
const GRID_TOP = 56
const GRID_BOTTOM = 164
const BASELINE = 200
const HISTORY = 6

function earliestDetection(metrics: LearningMetrics): [string, number] | null {
  const entries = Object.entries(metrics.time_to_detect ?? {})
  if (entries.length === 0) return null
  return entries.reduce((best, entry) => (entry[1] < best[1] ? entry : best))
}

function AccuracyChart({ rounds, detection }: { rounds: LearningRound[]; detection: [string, number] | null }) {
  const points = rounds.filter((round) => round.prediction_accuracy !== null)
  const values = points.map((round) => round.prediction_accuracy as number)
  let low = Math.floor(Math.min(...values) * 10) / 10
  let high = Math.ceil(Math.max(...values) * 10) / 10
  if (high - low < 0.1) {
    low = Math.max(0, low - 0.1)
    high = Math.min(1, low + 0.2)
  }
  const steps = Math.round((high - low) * 10)
  const xFor = (index: number) => (points.length === 1 ? CHART_LEFT : CHART_LEFT + (index * (CHART_RIGHT - CHART_LEFT)) / (points.length - 1))
  const yFor = (value: number) => GRID_BOTTOM - ((value - low) / (high - low)) * (GRID_BOTTOM - GRID_TOP)
  const gridValues = Array.from({ length: steps + 1 }, (_, index) => low + index / 10)
  const path = points.map((round, index) => `${index === 0 ? 'M' : 'L'}${xFor(index)} ${yFor(round.prediction_accuracy as number)}`).join('')
  const last = points.length - 1
  const lastX = xFor(last)
  const lastY = yFor(values[last])
  const detected = detection ? points.findIndex((round) => round.round === detection[1]) : -1
  const changedLast = Boolean(points[last]?.player_changed)
  return (
    <section className="flex grow basis-0 flex-col gap-4 rounded-md border-2 border-solid border-primary bg-surface px-6 pt-[20px] pb-4">
      <h2 className="text-base/sm font-bold text-text">How often the bot guessed your next move</h2>
      <div className="relative h-[236px] w-[600px] shrink-0">
        <svg width="600" height="236" viewBox="0 0 600 236" className="absolute top-0 left-0" role="img" aria-label={`How often the bot guessed your next move: ${points.map((round) => `round ${round.round} ${Math.round((round.prediction_accuracy as number) * 100)}%`).join(', ')}`}>
          <path d={gridValues.map((value) => `M${CHART_LEFT} ${yFor(value)}H${CHART_RIGHT}`).join('')} fill="none" stroke="#1D1B161F" />
          <path d={`M${CHART_LEFT} ${BASELINE}H${CHART_RIGHT}`} fill="none" stroke="#1D1B1666" />
          {points.map((round, index) =>
            round.player_changed ? (
              <path key={`changed-${round.round}`} d={`M${xFor(index)} 30V${BASELINE}`} fill="none" stroke="var(--color-bot)" strokeWidth="2" strokeDasharray="5 5" />
            ) : null
          )}
          <path d={path} fill="none" stroke="var(--color-primary)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
          {points.map((round, index) =>
            index === last ? (
              <circle key={round.round} cx={lastX} cy={lastY} r="7" fill="var(--color-primary)" />
            ) : (
              <circle key={round.round} cx={xFor(index)} cy={yFor(round.prediction_accuracy as number)} r="5" fill="var(--color-surface)" stroke="var(--color-primary)" strokeWidth="2.5" />
            )
          )}
        </svg>
        {gridValues.map((value) => (
          <span key={value} className="absolute -left-1 w-[38px] text-right font-mono text-[13px] leading-4 text-text-muted" style={{ top: yFor(value) - 8 }}>
            {Math.round(value * 100)}%
          </span>
        ))}
        {points.map((round, index) => (
          <span
            key={round.round}
            className={`absolute top-[212px] w-[40px] text-center font-mono text-sm leading-[18px] font-[600] ${index === last ? 'text-text' : 'text-text-muted'}`}
            style={{ left: xFor(index) - 20 }}
          >
            R{round.round}
          </span>
        ))}
        {points.map((round, index) =>
          round.player_changed ? (
            <span
              key={`adapted-${round.round}`}
              className="absolute top-[22px] text-sm leading-[18px] font-bold whitespace-nowrap text-bot-text"
              style={xFor(index) > 480 ? { right: 600 - xFor(index) + 10 } : { left: xFor(index) + 10 }}
            >
              you adapted
            </span>
          ) : null
        )}
        <span
          className="absolute w-[60px] text-right font-mono text-base/sm font-bold text-primary-text"
          style={changedLast ? { left: lastX - 72, top: lastY + 14 } : { left: lastX - 44, top: lastY - 33 }}
        >
          {Math.round(values[last] * 100)}%
        </span>
        {detection && detected >= 0 && (
          <span
            className="absolute flex items-center gap-[6px] whitespace-nowrap"
            style={{ left: Math.min(xFor(detected) - 4, 380), top: yFor(values[detected]) + 11 }}
          >
            <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden="true">
              <path d="M4 0L8 8H0Z" fill="var(--color-primary)" />
            </svg>
            <span className="text-[13px] leading-4 font-bold text-primary-text">Spotted your {habitShort(detection[0])} habit</span>
          </span>
        )}
      </div>
    </section>
  )
}

function Milestones({ metrics, rounds, exploited }: { metrics: LearningMetrics; rounds: LearningRound[]; exploited: string[] | undefined }) {
  const detection = earliestDetection(metrics)
  const first = rounds[0]
  const lastRound = rounds[rounds.length - 1]
  const earned = Object.entries(lastRound.habits)
    .filter(([key, habit]) => habit.fixed && !first.habits[key]?.fixed)
    .map(([key]) => habitName(key))
  const bandits = Object.entries(lastRound.bandit ?? {})
  const bandit = bandits.find(([key]) => isExploited(key.split('|')[0], exploited)) ?? bandits[0]
  const arms = bandit ? Object.entries(bandit[1]).sort((a, b) => b[1] - a[1]) : []
  return (
    <section className="flex w-[380px] shrink-0 flex-col gap-[18px] border-t-2 border-solid border-t-primary pt-4">
      <h2 className="text-[18px] leading-[22px] font-bold text-text">This set</h2>
      <div className="flex flex-col gap-[2px]">
        <span className="text-[36px] leading-[44px] font-[900] tracking-[-0.01em] text-text">
          {detection ? `${detection[1]} round${detection[1] === 1 ? '' : 's'}` : 'Still watching'}
        </span>
        <span className="text-base/base text-text">{detection ? `to spot your ${habitShort(detection[0])} habit` : 'no habit spotted yet'}</span>
      </div>
      <div className="flex flex-col gap-[2px]">
        <span className="text-[36px] leading-[44px] font-[900] tracking-[-0.01em] text-text">
          {earned.length === 0 ? 'No black belt yet' : `${earned.length} black belt${earned.length === 1 ? '' : 's'}`}
        </span>
        <span className="text-base/base text-text">{earned.length === 0 ? 'earned this set' : `earned this set: ${earned.join(', ')}`}</span>
      </div>
      {arms.length > 0 && (
        <div className="flex flex-col gap-3 border-t border-solid border-t-[#1D1B1626] pt-4">
          <div className="flex flex-col gap-1">
            <h3 className="text-base/sm font-bold text-text">When the bot went for your habit</h3>
            <span className="text-sm leading-[18px] text-text-muted">Estimated effectiveness</span>
          </div>
          {arms.map(([arm, rate]) => (
            <div key={arm} className="flex items-center gap-3">
              <span className="w-[112px] shrink-0 text-base/sm text-text">{optionName(arm)}</span>
              <Meter value={rate} />
              <span className="w-[52px] shrink-0 text-right text-lg/base font-[900] text-text">{Math.round(rate * 100)}%</span>
            </div>
          ))}
          <p className="text-sm leading-[18px] text-text-muted">The bot's estimate of how often each option works. Options it hasn&apos;t tried yet can keep their starting values.</p>
        </div>
      )}
    </section>
  )
}

function HabitsTable({ metrics, rounds, exploited }: { metrics: LearningMetrics; rounds: LearningRound[]; exploited: string[] | undefined }) {
  const lastRound = rounds[rounds.length - 1]
  const history = rounds.slice(-HISTORY)
  const rows = Object.entries(lastRound.habits)
    .map(([key, habit]) => ({ key, habit, target: isExploited(key, exploited) }))
    .sort((a, b) => Number(b.target) - Number(a.target) || (a.habit.mastery ?? 0) - (b.habit.mastery ?? 0))
  return (
    <section className="flex grow basis-0 flex-col border-t-2 border-solid border-t-primary pt-4">
      <div className="flex items-end gap-4 pb-2">
        <h2 className="grow basis-0 text-[18px] leading-[22px] font-bold text-text">Habits</h2>
        <span className="w-[118px] shrink-0 text-sm leading-[18px] font-medium text-text-muted">
          How well you&apos;ve learned the right answer, R{history[0].round} to R{history[history.length - 1].round}
        </span>
        <span className="w-[76px] shrink-0 text-right text-sm leading-[18px] font-medium text-text-muted">To detect</span>
        <span className="w-[76px] shrink-0 text-right text-sm leading-[18px] font-medium text-text-muted">To master</span>
      </div>
      {rows.map(({ key, habit, target }) => {
        const level = beltFor(habit.mastery, habit.fixed)
        const detect = metrics.time_to_detect?.[key]
        const master = metrics.time_to_mastery?.[key]
        const slipped = master !== undefined && !habit.fixed
        return (
          <div key={key} className="flex min-h-[56px] shrink-0 items-center gap-4 border-t border-solid border-t-[#1D1B161F] py-2">
            <span className="flex w-16 shrink-0">
              <Belt level={level} />
            </span>
            <span className="flex grow basis-0 flex-col">
              <span className="text-base leading-[22px] font-bold text-text">{habitName(key)}</span>
              <span className={`text-sm/sm ${target ? 'font-bold text-bot-text' : 'text-text-muted'}`}>
                {beltName(level)}
                {level.rank === 'black' ? ', fixed' : ''}
                {slipped ? `. Fixed in round ${master}, slipped since` : ''}
                {target ? '. The habit the bot is attacking right now.' : slipped ? '.' : ''}
              </span>
            </span>
            <span className="w-[118px] shrink-0">
              <BeltSquares rounds={history.map((round) => ({ round: round.round, ...(round.habits[key] ?? {}) }))} />
            </span>
            <span className={`w-[76px] shrink-0 text-right font-mono text-lg/base font-[600] ${detect === undefined ? 'text-text-muted' : 'text-text'}`}>
              {detect ?? '—'}
            </span>
            <span className={`w-[76px] shrink-0 text-right font-mono text-lg/base font-[600] ${master === undefined || slipped ? 'text-text-muted' : 'text-text'}`}>
              {master ?? '—'}
            </span>
          </div>
        )
      })}
    </section>
  )
}

function LearningSkeleton() {
  return (
    <>
      <div className="flex gap-12">
        <div className="flex w-[380px] shrink-0 flex-col justify-center gap-[14px]">
          <Skeleton className="h-[120px] w-[330px] rounded-md" />
          <Skeleton className="h-[22px] w-[300px]" />
          <Skeleton className="h-[22px] w-[180px]" />
          <Skeleton className="h-[18px] w-[120px]" faint />
        </div>
        <div className="flex h-[312px] grow basis-0 flex-col gap-[20px] rounded-md border-2 border-solid border-[#CFC8A0E6] p-6">
          <Skeleton className="h-[18px] w-[220px]" />
          <div className="flex grow basis-0 items-end border-b-2 border-solid border-b-[#CFC8A0E6]">
            <svg width="600" height="200" viewBox="0 0 600 200" aria-hidden="true">
              <path d="M20 150L128 128L236 108L344 116L452 84L560 68" fill="none" stroke="rgb(207 200 160 / 95%)" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
        </div>
      </div>
      <div className="flex items-start gap-12">
        <div className="flex w-[380px] shrink-0 flex-col gap-[18px] border-t-2 border-solid border-t-[#CFC8A0E6] pt-4">
          <Skeleton className="h-[18px] w-[90px]" />
          <Skeleton className="h-[36px] w-[180px]" />
          <Skeleton className="h-4 w-[220px]" faint />
          <Skeleton className="h-[36px] w-[220px]" />
          <Skeleton className="h-4 w-[200px]" faint />
        </div>
        <div className="flex grow basis-0 flex-col gap-[22px] border-t-2 border-solid border-t-[#CFC8A0E6] pt-4">
          <Skeleton className="h-[18px] w-[80px]" />
          {[200, 240, 170, 210].map((width) => (
            <div key={width} className="flex items-center gap-4">
              <Skeleton className="h-3 w-16 rounded-[3px]" />
              <div className="h-4 rounded-[4px] bg-[#CFC8A0BF]" style={{ width }} />
            </div>
          ))}
        </div>
      </div>
    </>
  )
}

function LearningBody({ sessionId }: { sessionId: string }) {
  const learning = useLearning(sessionId)
  const recording = useRecording(sessionId)
  const saving = useSavingRound(sessionId, learning.data?.rounds)
  const exploited = lastSummary(recording.data)?.exploited
  if (learning.isPending) return <LearningSkeleton />
  if (!learning.data) return null
  const rounds = [...learning.data.rounds].sort((a, b) => a.round - b.round)
  const withAccuracy = rounds.filter((round) => round.prediction_accuracy !== null)
  if (rounds.length === 0 || withAccuracy.length === 0) {
    if (saving !== null) return <SavingNote sessionId={sessionId} rounds={learning.data.rounds} />
    return <EmptyState headline="Round 1 is still going." line="Learning shows up when the round ends." />
  }
  const hero = withAccuracy[withAccuracy.length - 1]
  const heroPercent = Math.round((hero.prediction_accuracy as number) * 100)
  const first = withAccuracy[0]
  return (
    <>
      <SavingNote sessionId={sessionId} rounds={learning.data.rounds} />
      <div className="flex gap-12">
        <div className="flex w-[380px] shrink-0 flex-col justify-center gap-2">
          <span className={`w-max font-display ${heroPercent >= 100 ? 'text-[120px]' : 'text-[140px]'} leading-[136px] tracking-[-0.03em] text-text`}>
            {heroPercent}%
          </span>
          <span className="text-[22px] leading-[30px] font-bold text-text">
            of your next moves the bot
            <br />
            guessed right in round {hero.round}.
          </span>
          <span className="text-lg/lg text-text-muted">
            Round {first.round}: {Math.round((first.prediction_accuracy as number) * 100)}%.
          </span>
        </div>
        <AccuracyChart rounds={rounds} detection={earliestDetection(learning.data)} />
      </div>
      <div className="flex items-start gap-12">
        <Milestones metrics={learning.data} rounds={rounds} exploited={exploited} />
        <HabitsTable metrics={learning.data} rounds={rounds} exploited={exploited} />
      </div>
    </>
  )
}

export function Learning() {
  const { selectedId, sessions } = useFrame()
  const offline = useOfflineService(['analytics', 'brain'])
  return (
    <Screen title="Learning" picker gap="gap-8">
      <ScreenBanner
        service={offline}
        line={
          offline === 'brain'
            ? 'This is your last saved set. Live learning picks up when it reconnects.'
            : 'The numbers you see are the last ones it sent.'
        }
      />
      {sessions && sessions.length === 0 && (
        <EmptyState headline="Nothing to learn from yet." line="Play a set against Kumite and the learning panel fills in round by round." />
      )}
      {selectedId && <LearningBody key={selectedId} sessionId={selectedId} />}
    </Screen>
  )
}
