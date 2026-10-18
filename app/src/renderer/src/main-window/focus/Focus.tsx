import { useEffect, useState } from 'react'
import { Skeleton } from '../../design'
import { useInsights, type InsightEvent, type InsightLocation, type InsightMetricKey, type InsightsV1, type SessionMeta, type ServiceError } from '../../services'
import {
  earlySignal,
  eventText,
  fraction,
  locationText,
  METRIC_ORDER,
  metricLabel,
  momentOutcomes,
  outcomeWord,
  percentOf,
  signedAdvantage,
  type OutcomeWord
} from './words'

const PANEL = 'flex flex-col gap-4 rounded-md border-[1.5px] border-solid border-[#1D1B1626] bg-surface px-6 py-5'

function Tag({ children }: { children: string }) {
  return <span className="rounded-sm border-[1.5px] border-solid border-primary px-2 py-[2px] text-sm leading-[18px] font-bold text-primary-text">{children}</span>
}

function Mark({ success }: { success: boolean | null }) {
  if (success === null) {
    return (
      <svg width="14" height="14" viewBox="0 0 14 14" className="shrink-0" aria-hidden="true">
        <circle cx="7" cy="7" r="4" fill="currentColor" />
      </svg>
    )
  }
  return success ? (
    <svg width="14" height="14" viewBox="0 0 14 14" className="shrink-0" aria-hidden="true">
      <path d="M2.5 7.5l3 3 6-7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ) : (
    <svg width="14" height="14" viewBox="0 0 14 14" className="shrink-0" aria-hidden="true">
      <path d="M3 3l8 8M11 3l-8 8" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

function Outcomes({ outcomes }: { outcomes: OutcomeWord[] }) {
  return (
    <span className="flex w-[148px] shrink-0 flex-col gap-1">
      {outcomes.map((outcome, index) => (
        <span key={index} className={`flex items-center gap-2 text-sm leading-[20px] font-bold ${outcome.success ? 'text-good' : 'text-text'}`}>
          <Mark success={outcome.success} />
          {outcome.word}
        </span>
      ))}
    </span>
  )
}

function Detail({ event, response, humanSlot }: { event: InsightEvent; response: InsightLocation | null; humanSlot: number }) {
  const who = (slot: number | undefined) => (slot === undefined ? null : slot === humanSlot ? 'You' : 'The bot')
  const rows: [string, string | null][] = [
    ['Event', eventText(event)],
    ['By', who(event.actor)],
    ['Against', who(event.target)],
    ['Damage', typeof event.damage === 'number' ? String(event.damage) : null],
    ['Frame advantage', typeof event.frame_advantage === 'number' ? signedAdvantage(event.frame_advantage) : null],
    ['Move id', event.move_id === undefined ? null : String(event.move_id)],
    ['Response', response ? locationText(response) : 'None recorded']
  ]
  return (
    <dl className="grid grid-cols-[160px_1fr] gap-x-4 gap-y-1 pb-3 pl-[160px] text-base/sm">
      {rows.filter(([, value]) => value !== null).map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-text-muted">{label}</dt>
          <dd className="text-text">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

interface RowProps {
  id: string
  location: InsightLocation
  event: InsightEvent
  outcomes: OutcomeWord[]
  response: InsightLocation | null
  humanSlot: number
  open: string | null
  onToggle: (id: string) => void
}

function EventRow({ id, location, event, outcomes, response, humanSlot, open, onToggle }: RowProps) {
  const expanded = open === id
  return (
    <li className="border-t border-solid border-t-[#1D1B161F]">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => onToggle(id)}
        className="focus-ring flex w-full items-start gap-3 rounded-sm py-3 text-left hover:bg-[#1D1B160A]"
      >
        <Outcomes outcomes={outcomes} />
        <span className="text-base leading-[22px] text-text">
          <span className="font-mono text-sm text-text-muted">{locationText(location)}:</span> {eventText(event)}
        </span>
      </button>
      {expanded && <Detail event={event} response={response} humanSlot={humanSlot} />}
    </li>
  )
}

function evidenceMetric(data: InsightsV1): InsightMetricKey {
  if (data.focus.metric) return data.focus.metric
  return METRIC_ORDER.reduce((best, key) => (data.metrics[key].opportunities > data.metrics[best].opportunities ? key : best), METRIC_ORDER[0])
}

function MetricRow({ metricKey, data }: { metricKey: InsightMetricKey; data: InsightsV1 }) {
  const metric = data.metrics[metricKey]
  const invalid = data.quality === 'invalid' || metric.state === 'invalid'
  const text = invalid
    ? 'Data needs review'
    : metric.state === 'no_opportunities'
      ? 'No opportunities observed'
      : metric.state === 'early_signal'
        ? earlySignal(metricKey, metric, data.focus.min_opportunities)
        : fraction(metricKey, metric)
  const rate = invalid || metric.state === 'no_opportunities' ? '—' : percentOf(metric) ?? '—'
  return (
    <div className="flex items-baseline gap-4 border-t border-solid border-t-[#1D1B161F] py-2">
      <span className="w-[240px] shrink-0 text-base/sm font-bold text-text">{metricLabel(metric)}</span>
      <span className="grow basis-0 text-base/sm text-text">{text}</span>
      <span className="w-[56px] shrink-0 text-right font-mono text-base/sm font-bold text-text">{rate}</span>
    </div>
  )
}

function FocusCard({ data, stale }: { data: InsightsV1; stale: boolean }) {
  const { focus, freshness } = data
  const metric = focus.metric ? data.metrics[focus.metric] : null
  const invalid = data.quality === 'invalid'
  const through = freshness.latest_completed_round === null ? 'No completed rounds yet' : `Through completed round ${freshness.latest_completed_round}`
  return (
    <section className={PANEL} aria-label="What to practice">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-lg/base font-bold text-text">What to practice</h2>
          {focus.mode === 'manual' && <Tag>Selected focus</Tag>}
          {data.synthetic === true && <Tag>Synthetic example</Tag>}
          {data.synthetic === null && <Tag>Source type unknown</Tag>}
        </div>
        <span className="text-sm leading-[18px] text-text-muted">
          {through}
          {stale ? ' · Not up to date' : ''}
        </span>
      </div>
      {invalid ? (
        <p className="text-xl/lg font-bold text-text">This set&apos;s data needs review before it can suggest a focus.</p>
      ) : metric && focus.metric ? (
        <div className="flex flex-col gap-2">
          <span className="text-sm leading-[18px] font-bold text-primary-text">{metricLabel(metric)}</span>
          <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1">
            <span className="text-[30px] leading-[38px] font-bold text-text">{fraction(focus.metric, metric)}</span>
            {percentOf(metric) && <span className="font-display text-[30px] leading-[38px] text-primary">{percentOf(metric)}</span>}
          </div>
          <p className="text-base/sm text-text-muted">{focus.reason}</p>
          <p className="text-lg/lg font-bold text-text">{focus.action_reviewed && focus.action ? focus.action : 'Review these moments'}</p>
        </div>
      ) : (
        <p className="text-xl/lg font-bold text-text">{focus.reason}</p>
      )}
      <div className="flex flex-col">
        {METRIC_ORDER.map((key) => <MetricRow key={key} metricKey={key} data={data} />)}
      </div>
      {freshness.pending_learning_rounds.length > 0 && (
        <p role="status" className="text-base/sm text-text-muted">Round {freshness.pending_learning_rounds[0]} learning is still being saved.</p>
      )}
      {freshness.learning_ahead_rounds.length > 0 && (
        <p role="status" className="text-base/sm text-text-muted">Learning is ahead of the recording; waiting for it to catch up.</p>
      )}
    </section>
  )
}

function Lists({ data, humanSlot }: { data: InsightsV1; humanSlot: number }) {
  const [open, setOpen] = useState<string | null>(null)
  const key = evidenceMetric(data)
  const metric = data.metrics[key]
  const ids = new Set([
    ...metric.evidence.map((item) => `evidence:${item.opportunity.line}`),
    ...data.moments.map((moment) => `moment:${moment.reference.line}`)
  ])
  const present = open !== null && ids.has(open)

  useEffect(() => {
    if (open !== null && !present) setOpen(null)
  }, [open, present])

  const toggle = (id: string) => setOpen((current) => (current === id ? null : id))
  return (
    <div className="flex gap-12">
      <section className="flex grow basis-0 flex-col gap-2" aria-label="Evidence">
        <div className="flex items-baseline justify-between">
          <h3 className="text-base/sm font-bold text-text">Evidence: {metricLabel(metric).toLowerCase()}</h3>
          <span className="text-sm leading-[18px] text-text-muted">Showing {metric.evidence.length} of {metric.evidence_total}</span>
        </div>
        {metric.evidence.length === 0 ? (
          <p className="border-t border-solid border-t-[#1D1B161F] py-3 text-base/sm text-text-muted">No evidence for this metric yet.</p>
        ) : (
          <ul className="flex flex-col">
            {metric.evidence.map((item) => (
              <EventRow
                key={item.opportunity.line}
                id={`evidence:${item.opportunity.line}`}
                location={item.opportunity}
                event={item.event}
                outcomes={[outcomeWord(key, item.outcome)]}
                response={item.response}
                humanSlot={humanSlot}
                open={present ? open : null}
                onToggle={toggle}
              />
            ))}
          </ul>
        )}
      </section>
      <section className="flex grow basis-0 flex-col gap-2" aria-label="Moments">
        <div className="flex items-baseline justify-between">
          <h3 className="text-base/sm font-bold text-text">Moments</h3>
          <span className="text-sm leading-[18px] text-text-muted">Showing {data.moments.length} of {data.moments_total}</span>
        </div>
        {data.moments.length === 0 ? (
          <p className="border-t border-solid border-t-[#1D1B161F] py-3 text-base/sm text-text-muted">No moments recorded yet.</p>
        ) : (
          <ul className="flex flex-col">
            {data.moments.map((moment) => (
              <EventRow
                key={moment.reference.line}
                id={`moment:${moment.reference.line}`}
                location={moment.reference}
                event={moment.event}
                outcomes={momentOutcomes(moment)}
                response={moment.response}
                humanSlot={humanSlot}
                open={present ? open : null}
                onToggle={toggle}
              />
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

function unavailable(error: ServiceError | null): string {
  if (error?.kind === 'offline') return 'Insights come back when analytics reconnects.'
  if (error?.kind === 'not_found') return 'Analytics has no insights for this set yet.'
  return "Insights aren't available for this set right now."
}

export function Focus({ session }: { session: SessionMeta }) {
  const insights = useInsights(session.session_id, true)
  const data = insights.data?.session_id === session.session_id ? insights.data : undefined
  if (!data) {
    if (insights.isPending) {
      return (
        <section className={PANEL} aria-busy="true" aria-label="What to practice">
          <Skeleton className="h-6 w-[220px]" />
          <Skeleton className="h-10 w-[420px]" />
          <Skeleton className="h-5 w-[560px]" />
        </section>
      )
    }
    return (
      <section className={PANEL} aria-label="What to practice">
        <h2 className="text-lg/base font-bold text-text">What to practice</h2>
        <p className="text-base/sm text-text-muted">{unavailable(insights.error as ServiceError | null)}</p>
      </section>
    )
  }
  return (
    <>
      <FocusCard data={data} stale={insights.isError} />
      <Lists data={data} humanSlot={session.human_slot} />
    </>
  )
}
