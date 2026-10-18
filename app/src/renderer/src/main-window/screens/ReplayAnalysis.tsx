import { useEffect, useMemo, useState } from 'react'
import { Button, Check, Chip, EmptyState, Meter, optionName, RowChevron, situationName, Skeleton, withCommand } from '../../design'
import { useAnalyze, useReport, type DecisionPoint, type Report, type ReportHabit } from '../../services'
import { useFrame, type Focus } from '../frame'
import { Screen, ScreenBanner, useOfflineService } from '../Screen'

const FIRST_VISIBLE = 4
const ALL = '__all__'

type Direction = [number, number]

const DIRECTIONS: Record<string, Direction> = {
  ub: [-1, -1],
  u: [0, -1],
  uf: [1, -1],
  b: [-1, 0],
  f: [1, 0],
  db: [-1, 1],
  d: [0, 1],
  df: [1, 1]
}

function leadingDirection(command: string): { direction: Direction; alone: boolean } | null {
  const match = /^([udfb])\/?([udfb])?(?=$|[+\s,])/.exec(command.trim())
  if (!match) return null
  const key = `${match[1]}${match[2] ?? ''}`
  const direction = DIRECTIONS[key]
  if (!direction) return null
  return { direction, alone: match[0].length === command.trim().length }
}

function DirectionPad({ direction }: { direction: Direction }) {
  const [dx, dy] = direction
  const cells = [-1, 0, 1].flatMap((row) => [-1, 0, 1].map((column) => [column, row] as Direction))
  const cx = 46 + dx * 31
  const cy = 46 + dy * 31
  const diagonal = dx !== 0 && dy !== 0
  const reach = diagonal ? 6 : 8
  const ex = cx + dx * reach
  const ey = cy + dy * reach
  const head = diagonal
    ? `M${ex} ${ey - 8 * dy}V${ey}H${ex - 8 * dx}`
    : `M${ex - 5 * dx + 5 * dy} ${ey - 5 * dy + 5 * dx}L${ex} ${ey}L${ex - 5 * dx - 5 * dy} ${ey - 5 * dy - 5 * dx}`
  return (
    <svg width="92" height="92" viewBox="0 0 92 92" aria-hidden="true" className="shrink-0">
      {cells.map(([column, row]) => {
        if (column === 0 && row === 0) return null
        const target = column === dx && row === dy
        return (
          <rect
            key={`${column}${row}`}
            x={1 + (column + 1) * 31}
            y={1 + (row + 1) * 31}
            width="28"
            height="28"
            rx="5"
            fill={target ? 'var(--color-primary)' : 'none'}
            stroke={target ? 'none' : '#1D1B1640'}
            strokeWidth="1.5"
          />
        )
      })}
      <circle cx="46" cy="46" r="8" fill="var(--color-track)" stroke="#1D1B1659" strokeWidth="1.5" />
      <path d={`M${46 + dx * 8} ${46 + dy * 8}L${cx - dx * 8} ${cy - dy * 8}`} fill="none" stroke="var(--color-primary)" strokeWidth="2" strokeDasharray="3 3" />
      <path
        d={`M${cx - dx * reach} ${cy - dy * reach}L${ex} ${ey}${head}`}
        fill="none"
        stroke="var(--color-overlay-text)"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function commandOf(point: DecisionPoint, name: string): string | undefined {
  return point.options.find((option) => option.name === name)?.command
}

function TopHabit({ report, habit }: { report: Report; habit: ReportHabit }) {
  const moments = habit.moments ?? []
  const lost = report.decision_points
    .filter((point) => moments.includes(point.frame))
    .reduce((sum, point) => sum + (point.cost ?? 0), 0)
  const first = report.decision_points.find((point) => point.frame === moments[0])
  const command = first ? commandOf(first, first.best) : undefined
  const move = command ? leadingDirection(command) : null
  return (
    <section className="flex items-center gap-8 rounded-md border-2 border-solid border-primary bg-surface px-[28px] py-6">
      {command && (
        <div className="flex shrink-0 flex-col items-center gap-2">
          {move && <DirectionPad direction={move.direction} />}
          <span className="font-mono text-base/sm font-bold text-primary-text">
            {move?.alone ? 'hold' : 'press'} {command}
          </span>
        </div>
      )}
      <div className="flex grow basis-0 flex-col gap-2">
        <span className="text-base/sm font-medium text-text-muted">Your top habit, and the smallest fix for it</span>
        <h2 className="font-display text-xl leading-[38px] tracking-tight text-primary-text">{habit.min_change}</h2>
        <p className="text-base/base text-text">
          You did this in {Math.round(habit.p * 100)}% of these spots, {habit.count} times this set.
        </p>
      </div>
      <div className="w-px shrink-0 self-stretch bg-[#1D1B1626]" />
      <div className="flex w-[150px] shrink-0 flex-col gap-[2px]">
        <span className="text-[36px] leading-[44px] font-[900] tracking-[-0.01em] text-text">{lost}</span>
        <span className="text-base/base text-text">damage lost to this habit</span>
      </div>
    </section>
  )
}

function ExpandedPoint({ point }: { point: DecisionPoint }) {
  const options = [...point.options].sort((a, b) => (a.name === point.best ? -1 : b.name === point.best ? 1 : b.p - a.p))
  return (
    <div className="flex flex-col gap-[20px] px-[28px] pt-[22px] pb-6">
      <div className="flex items-start justify-between gap-6">
        <div className="flex flex-col gap-1">
          <span className="text-[15px] leading-[18px] font-medium text-text-muted">
            Round {point.round}, frame {point.frame}
          </span>
          <span className="text-[22px] leading-[30px] font-bold text-text">{situationName(point.situation)}</span>
        </div>
        {point.cost !== undefined && (
          <span className="flex items-baseline gap-2">
            <span className="text-xl leading-[34px] font-[900] text-text">{point.cost}</span>
            <span className="text-base/sm text-text-muted">damage</span>
          </span>
        )}
      </div>
      <div className="flex items-start gap-[36px]">
        <div className="flex w-[220px] shrink-0 flex-col gap-[14px]">
          <div className="flex flex-col gap-[2px]">
            <span className="text-sm leading-[18px] font-medium text-text-muted">You did</span>
            <span className="text-lg/lg font-medium text-text">{withCommand(optionName(point.actual), commandOf(point, point.actual))}</span>
          </div>
          <div className="flex flex-col gap-[2px]">
            <span className="text-sm leading-[18px] font-medium text-text-muted">Best option</span>
            <span className="text-lg/lg font-bold text-primary-text">{withCommand(optionName(point.best), commandOf(point, point.best))}</span>
          </div>
        </div>
        <div className="flex w-[392px] shrink-0 flex-col gap-3 pt-[2px]">
          {options.map((option) => {
            const best = option.name === point.best
            return (
              <div key={option.name} className="flex items-center gap-3">
                <span className={`w-[84px] shrink-0 text-base/sm text-text ${best ? 'font-bold' : 'font-medium'}`}>{optionName(option.name)}</span>
                <Meter value={option.p} strong={best} />
                <span className={`w-[44px] shrink-0 text-right font-mono text-base/sm text-text ${best ? 'font-bold' : ''}`}>
                  {Math.round(option.p * 100)}%
                </span>
                <span className="w-[72px] shrink-0 text-sm leading-[18px] font-bold text-text">
                  {option.name === point.actual ? 'your pick' : ''}
                </span>
              </div>
            )
          })}
        </div>
        {point.why && (
          <div className="flex grow basis-0 flex-col gap-1">
            <span className="text-sm leading-[18px] font-medium text-text-muted">Why</span>
            <p className="text-base/base text-text">{point.why}</p>
          </div>
        )}
      </div>
    </div>
  )
}

function CollapsedPoint({ point, onOpen }: { point: DecisionPoint; onOpen: () => void }) {
  const cost = point.cost ?? 0
  return (
    <button type="button" onClick={onOpen} aria-expanded={false} className="focus-ring flex h-[60px] w-full shrink-0 items-center gap-[20px] pr-[20px] pl-[28px] text-left">
      <span className="w-[160px] shrink-0 text-[15px] leading-[18px] font-medium text-text-muted">
        Round {point.round}, frame {point.frame}
      </span>
      <span className="grow basis-0 truncate text-base/sm font-bold text-text">{situationName(point.situation)}</span>
      {point.good ? (
        <span className="flex w-[260px] shrink-0 items-center gap-2 text-base/sm font-bold text-good">
          <Check />
          {optionName(point.actual)}. Right call
        </span>
      ) : (
        <span className="w-[260px] shrink-0 text-base/sm text-text">
          {optionName(point.actual)}. Best: {optionName(point.best).toLowerCase()}
        </span>
      )}
      <span className={`w-[96px] shrink-0 text-right text-base/sm font-[900] ${point.good ? 'text-good' : 'text-text'}`}>
        {point.good ? `+${cost}` : `−${cost}`}
      </span>
      <RowChevron open={false} />
    </button>
  )
}

function pointKey(point: DecisionPoint): string {
  return `${point.round}:${point.frame}`
}

function DecisionPoints({ report, focus }: { report: Report; focus: Focus | null }) {
  const situations = useMemo(() => {
    const counts = new Map<string, number>()
    report.decision_points.forEach((point) => counts.set(point.situation, (counts.get(point.situation) ?? 0) + 1))
    return [...counts.entries()]
  }, [report])
  const [filter, setFilter] = useState(ALL)
  const [openKey, setOpenKey] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)

  useEffect(() => {
    if (!focus) return
    setFilter(ALL)
    setShowAll(true)
    const match = report.decision_points.find((point) => point.round === focus.round && point.frame === focus.frame)
    setOpenKey(match ? pointKey(match) : null)
  }, [focus, report])

  const filtered = report.decision_points.filter((point) => filter === ALL || point.situation === filter)
  const visible = showAll ? filtered : filtered.slice(0, FIRST_VISIBLE)
  const expandedKey = openKey && filtered.some((point) => pointKey(point) === openKey) ? openKey : filtered[0] ? pointKey(filtered[0]) : null
  const expanded = visible.find((point) => pointKey(point) === expandedKey)
  const collapsed = visible.filter((point) => pointKey(point) !== expandedKey)
  const hidden = filtered.length - visible.length

  const choose = (next: string) => {
    setFilter(next)
    setOpenKey(null)
    setShowAll(false)
  }

  if (report.decision_points.length === 0) return <p className="text-lg/lg text-text-muted">No decision points in this set.</p>

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <span className="pr-2 text-base/sm font-medium text-text-muted">Situation</span>
        <Chip label="All" count={report.decision_points.length} selected={filter === ALL} onSelect={() => choose(ALL)} />
        {situations.map(([situation, count]) => (
          <Chip key={situation} label={situationName(situation)} count={count} selected={filter === situation} onSelect={() => choose(situation)} />
        ))}
      </div>
      <div className="flex flex-col gap-4">
        {expanded && (
          <div className="rounded-md border border-solid border-[#1D1B161F] bg-surface">
            <ExpandedPoint point={expanded} />
          </div>
        )}
        {(collapsed.length > 0 || hidden > 0) && (
          <div className="flex flex-col overflow-clip rounded-md border border-solid border-[#1D1B161F] bg-surface">
            {collapsed.map((point, index) => (
              <div key={pointKey(point)} className={index > 0 ? 'border-t border-solid border-t-[#1D1B161A]' : ''}>
                <CollapsedPoint point={point} onOpen={() => setOpenKey(pointKey(point))} />
              </div>
            ))}
            {hidden > 0 && (
              <button
                type="button"
                onClick={() => setShowAll(true)}
                className={`focus-ring flex h-12 shrink-0 items-center justify-center text-base/sm font-bold text-primary-text ${
                  collapsed.length > 0 ? 'border-t border-solid border-t-[#1D1B161A]' : ''
                }`}
              >
                Show {hidden} more {filter === ALL ? '' : 'in this situation'}
              </button>
            )}
          </div>
        )}
      </div>
    </>
  )
}

function NotAnalyzed({ sessionId }: { sessionId: string }) {
  const analyze = useAnalyze(sessionId)
  return (
    <EmptyState headline="This set hasn't been analyzed yet." line="Kumite's replay service scores every decision you made. It takes a minute or two.">
      <div className="flex flex-col items-start gap-3">
        <Button disabled={analyze.isPending} onClick={() => analyze.mutate()}>
          {analyze.isPending ? 'Analyzing…' : 'Analyze this set'}
        </Button>
        {analyze.isError && <p className="text-base/sm text-text-muted">{analyze.error.message}</p>}
      </div>
    </EmptyState>
  )
}

function ReplaySkeleton() {
  return (
    <>
      <Skeleton className="h-[172px] w-full rounded-md" />
      <div className="flex gap-2">
        {[80, 180, 110, 120].map((width) => (
          <Skeleton key={width} className="h-[36px] rounded-[18px]" faint />
        ))}
      </div>
      <Skeleton className="h-[230px] w-full rounded-md" faint />
    </>
  )
}

function ReplayBody({ sessionId }: { sessionId: string }) {
  const { focus } = useFrame()
  const report = useReport(sessionId)
  if (report.isPending) return <ReplaySkeleton />
  if (report.isError && report.data === undefined) return null
  if (report.data === null) return <NotAnalyzed sessionId={sessionId} />
  if (!report.data) return null
  const top = report.data.habits[0]
  return (
    <>
      {top && <TopHabit report={report.data} habit={top} />}
      <DecisionPoints report={report.data} focus={focus} />
    </>
  )
}

export function ReplayAnalysis() {
  const { selectedId, sessions } = useFrame()
  const offline = useOfflineService(['replay', 'brain'])
  return (
    <Screen title="Replay analysis" picker>
      <ScreenBanner service={offline} line="The analysis you see is the last one it sent." />
      {sessions && sessions.length === 0 && (
        <EmptyState headline="No set to analyze yet." line="Play a set against Kumite and its analysis shows up here." />
      )}
      {selectedId && <ReplayBody key={selectedId} sessionId={selectedId} />}
    </Screen>
  )
}
