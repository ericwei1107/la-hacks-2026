import type { ChatReply, ChatRequest, Report } from './contracts'
import { requestJson, ServiceError, TIMEOUTS } from './http'

export async function getReport(sessionId: string): Promise<Report | null> {
  try {
    return await requestJson<Report>({
      service: 'replay',
      call: 'getReport',
      path: ['reports', sessionId],
      timeoutMs: TIMEOUTS.standard,
      expect: 'object'
    })
  } catch (error) {
    if (error instanceof ServiceError && error.kind === 'not_found') return null
    throw error
  }
}

const analyzing = new Map<string, Promise<Report>>()

export function analyze(sessionId: string): Promise<Report> {
  const pending = analyzing.get(sessionId)
  if (pending) return pending
  const request = requestJson<Report>({
    service: 'replay',
    call: 'analyze',
    path: ['analyze', sessionId],
    method: 'POST',
    timeoutMs: TIMEOUTS.analyze,
    expect: 'object'
  }).finally(() => analyzing.delete(sessionId))
  analyzing.set(sessionId, request)
  return request
}

export function chat(request: ChatRequest): Promise<ChatReply> {
  return requestJson({
    service: 'replay',
    call: 'chat',
    path: ['coach', 'chat'],
    method: 'POST',
    body: request,
    timeoutMs: TIMEOUTS.chat,
    expect: 'object'
  })
}
