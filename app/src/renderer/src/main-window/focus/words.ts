import type { InsightEvent, InsightLocation, InsightMetric, InsightMetricKey, InsightMoment } from '../../services'

interface MetricWords {
  one: string
  many: string
  seenOne: string
  seenMany: string
  done: string
  success: string
  failure: string
}

const METRIC_WORDS: Record<InsightMetricKey, MetricWords> = {
  low_defense: { one: 'low', many: 'lows', seenOne: 'low', seenMany: 'lows', done: 'blocked', success: 'Blocked', failure: 'Not blocked' },
  throw_defense: { one: 'throw', many: 'throws', seenOne: 'throw', seenMany: 'throws', done: 'broken', success: 'Broken', failure: 'Not broken' },
  punish_conversion: { one: 'punish', many: 'punishes', seenOne: 'punish chance', seenMany: 'punish chances', done: 'landed', success: 'Punished', failure: 'Not punished' }
}

const KINDS: Record<string, string> = {
  counter_hit: 'counter-hit',
  hit: 'hit',
  block: 'block',
  throw: 'throw',
  throw_break: 'throw break',
  whiff: 'whiff',
  knockdown: 'knockdown'
}

export const METRIC_ORDER: InsightMetricKey[] = ['low_defense', 'throw_defense', 'punish_conversion']

export interface OutcomeWord {
  word: string
  success: boolean | null
}

function noun(key: InsightMetricKey, count: number): string {
  return count === 1 ? METRIC_WORDS[key].one : METRIC_WORDS[key].many
}

function signed(value: number): string {
  if (value > 0) return `+${value}`
  if (value < 0) return `−${Math.abs(value)}`
  return '0'
}

export function metricLabel(metric: InsightMetric): string {
  return metric.estimated && !/estimated/i.test(metric.label) ? `Estimated ${metric.label.toLowerCase()}` : metric.label
}

export function fraction(key: InsightMetricKey, metric: InsightMetric): string {
  return `${metric.successes} of ${metric.opportunities} ${noun(key, metric.opportunities)} ${METRIC_WORDS[key].done}`
}

export function percentOf(metric: InsightMetric): string | null {
  return typeof metric.value === 'number' ? `${Math.round(metric.value * 100)}%` : null
}

export function earlySignal(key: InsightMetricKey, metric: InsightMetric, threshold: number | undefined): string {
  const words = METRIC_WORDS[key]
  const seen = `${metric.opportunities} ${metric.opportunities === 1 ? words.seenOne : words.seenMany} seen`
  return threshold === undefined ? `${seen}; more needed for an automatic focus` : `${seen}; need ${threshold} for an automatic focus`
}

export function locationText(location: InsightLocation): string {
  return `Round ${location.round}, frame ${location.frame ?? '—'}`
}

export function eventText(event: InsightEvent): string {
  const kind = KINDS[event.kind] ?? event.kind.replace(/_/g, ' ')
  const level = event.hit_level && !['none', 'throw'].includes(event.hit_level) ? `${event.hit_level.replace(/_/g, ' ')} ` : ''
  const parts = [`${level}${kind}`]
  if (typeof event.damage === 'number' && event.damage > 0) parts.push(`${event.damage} damage`)
  if (event.kind === 'block' && typeof event.frame_advantage === 'number') parts.push(`${signed(event.frame_advantage)} on block`)
  return parts.join(', ')
}

export function outcomeWord(key: InsightMetricKey | undefined, outcome: 'success' | 'failure'): OutcomeWord {
  if (!key) return { word: outcome === 'success' ? 'Success' : 'Missed', success: outcome === 'success' }
  return { word: outcome === 'success' ? METRIC_WORDS[key].success : METRIC_WORDS[key].failure, success: outcome === 'success' }
}

export function momentOutcomes(moment: InsightMoment): OutcomeWord[] {
  if (moment.outcome === 'damage') return [{ word: 'Took damage', success: null }]
  if (moment.outcome === 'mixed') {
    return METRIC_ORDER.flatMap((key) => {
      const entry = moment.metric_outcomes[key]
      return entry ? [outcomeWord(key, entry.outcome)] : []
    })
  }
  return [outcomeWord(moment.metrics[0], moment.outcome)]
}

export function signedAdvantage(value: number): string {
  return signed(value)
}
