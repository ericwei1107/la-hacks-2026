import { useState } from 'react'
import { characterName, dayLabel, EmptyState, habitShort, notation, oneDecimal, percent, Select, share, shortClock, Skeleton, situationName } from '../../design'
import { useRecording, useStats, useTrends, type SessionMeta, type SessionStats, type TrendPoint } from '../../services'
import { SavingNote, useFrame } from '../frame'
import { Focus } from '../focus/Focus'
import { Screen, ScreenBanner, useOfflineService } from '../Screen'
import { isExploited, lastSummary, throwCounts } from '../setData'

type StatKey = 'low_block_rate' | 'punish_rate' | 'throw_break_rate' | 'counter_hits_taken' | 'counter_hits_given'

const STAT_LABELS: Record<StatKey, string> = {
  low_block_rate: 'Low block rate',
  punish_rate: 'Punish rate',
  throw_break_rate: 'Throw break rate',
  counter_hits_taken: 'Counter hits taken',
  counter_hits_given: 'Counter hits given'
}

const RATES: StatKey[] = ['low_block_rate', 'punish_rate', 'throw_break_rate']
const HISTORY = 5
const TALLEST_BAR = 112

function formatStat(stat: StatKey, value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return RATES.includes(stat) ? percent(value) : String(Math.round(value))
}

function changeSince(stat: StatKey, current: number | null | undefined, previous: number | null | undefined): number | null {
  if (current === null || current === undefined || previous === null || previous === undefined) return null
  return RATES.includes(stat) ? Math.round(current * 100) - Math.round(previous * 100) : Math.round(current - previous)
}

function sortedSeries(series: TrendPoint[]): TrendPoint[] {
  return [...series].sort((a, b) => new Date(a.started_at).getTime() - new Date(b.started_at).getTime())
}

function previousPoint(series: TrendPoint[], session: SessionMeta): TrendPoint | undefined {
  const index = series.findIndex((point) => point.session_id === session.session_id)
  if (index > 0) return series[index - 1]
  if (index === 0) return undefined
  const start = new Date(session.started_at).getTime()
  return [...series].reverse().find((point) => new Date(point.started_at).getTime() < start)
}

function habitPhrase(key: string): string {
  if (key.startsWith('after_block:')) return notation(key.slice('after_block:'.length))
  return habitShort(key)
}

function SmallStat({ value, label, note, divided }: { value: string; label: string; note: string | null; divided?: boolean }) {
  return (
    <div className={`flex w-[190px] shrink-0 flex-col justify-end gap-1 pt-4 pr-[20px] pb-[18px] pl-6 ${divided ? 'border-l border-solid border-l-[#1D1B161F]' : ''}`}>
      <span className="text-[32px] leading-[40px] font-[900] tracking-[-0.01em] text-text">{value}</span>
      <span className="text-base/sm font-bold text-text">{label}</span>
      <span className="text-sm leading-[18px] font-medium text-text-muted">{note ?? '\u00a0'}</span>
    </div>
  )
}

function vsLast(change: number | null): string | null {
  if (change === null) return null
  return `${change > 0 ? '+' : change < 0 ? '−' : ''}${Math.abs(change)} vs last set`
}

function Headline({ stats, session, previous, exploited, throws }: {
  stats: SessionStats
  session: SessionMeta
  previous: TrendPoint | undefined
  exploited: string[] | undefined
  throws: { broken: number; total: number } | null
}) {
  const totals = stats.totals
  const low = totals.low_block_rate
  const lowChange = changeSince('low_block_rate', low, previous?.values.low_block_rate)
  const hunted = exploited?.includes('low_defense') ? `This is the habit ${characterName(session.bot_character)} is hunting.` : ''
  const lowNote =
    low === null
      ? "Didn't come up this set"
      : [
          lowChange === null ? '' : lowChange < 0 ? `Down ${-lowChange} from last set.` : lowChange > 0 ? `Up ${lowChange} from last set.` : 'Same as last set.',
          hunted
        ]
          .filter(Boolean)
          .join(' ')
  const rounds = Math.max(stats.rounds.length, 1)
  return (
    <div className="flex border-t-2 border-b border-solid border-t-primary border-b-[#1D1B161F]">
      <div className="flex grow basis-0 flex-col justify-end gap-1 pt-[20px] pr-12 pb-6">
        <span className="text-[72px] leading-[76px] font-[900] tracking-tight text-text">{percent(low)}</span>
        <span className="text-[18px] leading-[22px] font-bold text-text">Low block rate</span>
        {lowNote && <span className="text-sm leading-[18px] font-medium text-text-muted">{lowNote}</span>}
      </div>
      <div className="flex w-[380px] shrink-0 flex-col border-l border-solid border-l-[#1D1B161F]">
        <div className="flex grow basis-0">
          <SmallStat
            value={percent(totals.punish_rate)}
            label="Punish rate"
            note={totals.punish_rate === null ? "Didn't come up this set" : vsLast(changeSince('punish_rate', totals.punish_rate, previous?.values.punish_rate))}
          />
          <SmallStat
            value={percent(totals.throw_break_rate)}
            label="Throw break rate"
            note={totals.throw_break_rate === null ? "Didn't come up this set" : throws && throws.total > 0 ? `${throws.broken} of ${throws.total} broken` : null}
            divided
          />
        </div>
        <div className="flex grow basis-0 border-t border-solid border-t-[#1D1B161F]">
          <SmallStat value={String(totals.counter_hits_taken)} label="Counter hits taken" note={`${oneDecimal(totals.counter_hits_taken / rounds)} per round`} />
          <SmallStat
            value={String(totals.counter_hits_given)}
            label="Counter hits given"
            note={vsLast(changeSince('counter_hits_given', totals.counter_hits_given, previous?.values.counter_hits_given))}
            divided
          />
        </div>
      </div>
    </div>
  )
}

function DamageBySituation({ stats, exploited }: { stats: SessionStats; exploited: string[] | undefined }) {
  const entries = Object.entries(stats.totals.damage_taken_by_situation).sort((a, b) => b[1] - a[1])
  const total = entries.reduce((sum, [, value]) => sum + value, 0)
  const largest = Math.max(...entries.map(([, value]) => value), 1)
  const hunted = entries.find(([key, value]) => value > 0 && isExploited(key, exploited))
  return (
    <section className="flex grow basis-0 flex-col gap-[22px]">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg/base font-bold text-text">Damage taken by situation</h2>
        <span className="text-sm leading-[18px] font-medium text-text-muted">{total} total</span>
      </div>
      {entries.map(([key, value]) => {
        const target = isExploited(key, exploited)
        return (
          <div key={key} className="flex items-center gap-4">
            <span className={`w-[180px] shrink-0 text-base/sm text-text ${target ? 'font-bold' : 'font-medium'}`}>
              {situationName(key)}
              {target && <span className="sr-only">, the habit the bot is attacking right now</span>}
            </span>
            <div className="flex h-[20px] grow basis-0">
              <div className={`h-full rounded-[3px] ${target ? 'bg-bot' : 'bg-text-muted/45'}`} style={{ width: `${(value / largest) * 100}%` }} />
            </div>
            <span className="w-12 shrink-0 text-right font-mono text-base/sm font-[600] text-text">{value}</span>
          </div>
        )
      })}
      {hunted && total > 0 && (
        <p className="mt-auto border-t border-solid border-t-[#1D1B161F] pt-[18px] text-lg/lg font-bold text-text">
          Fix the {habitPhrase(hunted[0])} habit and you cut {share(hunted[1], total)} of the damage you take.
        </p>
      )}
    </section>
  )
}

function AcrossSessions({ series, session }: { series: TrendPoint[]; session: SessionMeta }) {
  const [stat, setStat] = useState<StatKey>('low_block_rate')
  const end = series.findIndex((point) => point.session_id === session.session_id)
  const upTo = end >= 0 ? series.slice(0, end + 1) : series
  const shown = upTo.slice(-HISTORY)
  const largest = Math.max(...shown.map((point) => point.values[stat] ?? 0), 0.0001)
  return (
    <section className="flex w-[380px] shrink-0 flex-col gap-[20px] rounded-md border-2 border-solid border-primary bg-surface px-6 py-[20px]">
      <div className="flex items-center justify-between">
        <h2 className="text-lg/base font-bold text-text">Across sessions</h2>
        <Select size="compact" aria-label="Stat" value={stat} onChange={(event) => setStat(event.currentTarget.value as StatKey)}>
          {(Object.keys(STAT_LABELS) as StatKey[]).map((key) => (
            <option key={key} value={key}>
              {STAT_LABELS[key]}
            </option>
          ))}
        </Select>
      </div>
      <div className="flex h-[200px] shrink-0 items-end justify-between border-b-[1.5px] border-solid border-b-[#1D1B1666] px-2">
        {shown.map((point) => {
          const current = point.session_id === session.session_id
          const value = point.values[stat]
          return (
            <div key={point.session_id} className="flex w-[52px] shrink-0 flex-col items-center gap-[6px]">
              <span className={`font-mono ${current ? 'text-base/sm font-bold text-primary-text' : 'text-sm leading-[18px] font-[600] text-text-muted'}`}>
                {formatStat(stat, value)}
              </span>
              <div
                className={`w-[44px] shrink-0 rounded-t-[3px] ${current ? 'bg-primary' : 'bg-text-muted/45'}`}
                style={{ height: Math.max(2, ((value ?? 0) / largest) * TALLEST_BAR) }}
              />
            </div>
          )
        })}
      </div>
      <div className="-mt-2 flex justify-between px-2">
        {shown.map((point) => {
          const current = point.session_id === session.session_id
          return (
            <div key={point.session_id} className="flex w-[52px] shrink-0 flex-col items-center">
              <span className={`font-mono text-sm leading-[18px] ${current ? 'font-bold text-primary-text' : 'text-text'}`}>{shortClock(point.started_at)}</span>
              <span className="text-[13px] leading-4 text-text-muted">{dayLabel(point.started_at)}</span>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function StatsSkeleton() {
  return (
    <>
      <div className="flex gap-12 border-t-2 border-solid border-t-[#CFC8A0E6] pt-6">
        <div className="flex grow basis-0 flex-col justify-end gap-3">
          <Skeleton className="h-[72px] w-[200px] rounded-md" />
          <Skeleton className="h-[22px] w-[160px]" />
          <Skeleton className="h-4 w-[320px]" faint />
        </div>
        <Skeleton className="h-[200px] w-[380px] rounded-md" faint />
      </div>
      <div className="flex gap-12">
        <div className="flex grow basis-0 flex-col gap-[22px]">
          {[90, 70, 62, 56, 52].map((width) => (
            <div key={width} className="flex items-center gap-4">
              <Skeleton className="h-4 w-[180px]" faint />
              <div className="h-[20px] rounded-[3px] bg-[#CFC8A0BF]" style={{ width: `${width * 4}px` }} />
            </div>
          ))}
        </div>
        <Skeleton className="h-[320px] w-[380px] rounded-md" faint />
      </div>
    </>
  )
}

function StatsBody({ session }: { session: SessionMeta }) {
  const stats = useStats(session.session_id)
  const trends = useTrends(session.player, session.human_character)
  const recording = useRecording(session.session_id)
  if (stats.isPending) return <StatsSkeleton />
  if (!stats.data) return null
  const series = sortedSeries(trends.data?.series ?? [])
  const previous = previousPoint(series, session)
  const exploited = lastSummary(recording.data)?.exploited
  const throws = recording.data ? throwCounts(recording.data.events, session.human_slot) : null
  return (
    <>
      <SavingNote sessionId={session.session_id} rounds={stats.data.rounds} />
      <Headline stats={stats.data} session={session} previous={previous} exploited={exploited} throws={throws} />
      <div className="flex gap-12">
        <DamageBySituation stats={stats.data} exploited={exploited} />
        {series.length > 0 && <AcrossSessions series={series} session={session} />}
      </div>
    </>
  )
}

export function Stats() {
  const { selected, sessions } = useFrame()
  const offline = useOfflineService(['analytics', 'brain'])
  return (
    <Screen title="Stats" picker>
      <ScreenBanner service={offline} line="The numbers you see are the last ones it sent." />
      {sessions && sessions.length === 0 && <EmptyState headline="No stats yet." line="Play a set against Kumite and its numbers show up here." />}
      {selected && window.kumite?.insights === true && <Focus key={`focus:${selected.session_id}`} session={selected} />}
      {selected && <StatsBody key={selected.session_id} session={selected} />}
    </Screen>
  )
}
