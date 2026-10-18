import type { InsightsV1, LearningMetrics, SessionStats, Trends } from './contracts'
import { requestJson, TIMEOUTS } from './http'

export function getStats(sessionId: string): Promise<SessionStats> {
  return requestJson({
    service: 'analytics',
    call: 'getStats',
    path: ['stats', sessionId],
    timeoutMs: TIMEOUTS.standard,
    expect: 'object'
  })
}

export function getTrends(player: string, character: string, stat?: string): Promise<Trends> {
  return requestJson({
    service: 'analytics',
    call: 'getTrends',
    path: ['trends', player, character],
    query: { stat },
    timeoutMs: TIMEOUTS.standard,
    expect: 'object'
  })
}

export function getLearning(sessionId: string): Promise<LearningMetrics> {
  return requestJson({
    service: 'analytics',
    call: 'getLearning',
    path: ['learning', sessionId],
    timeoutMs: TIMEOUTS.standard,
    expect: 'object'
  })
}

export const INSIGHT_MOMENTS = 3

export function getInsights(sessionId: string): Promise<InsightsV1> {
  return requestJson({
    service: 'analytics',
    call: 'getInsights',
    path: ['insights', sessionId],
    query: { limit: String(INSIGHT_MOMENTS) },
    timeoutMs: TIMEOUTS.standard,
    expect: 'object'
  })
}
