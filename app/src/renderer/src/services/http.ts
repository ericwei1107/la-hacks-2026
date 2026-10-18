import type { ServiceName } from '../../../shared/bridge'
import { serviceUrl } from './addresses'

export type ServiceErrorKind = 'offline' | 'timeout' | 'not_found' | 'http' | 'bad_response'

export class ServiceError extends Error {
  readonly service: ServiceName
  readonly call: string
  readonly kind: ServiceErrorKind
  readonly status?: number

  constructor(service: ServiceName, call: string, kind: ServiceErrorKind, message: string, status?: number) {
    super(message)
    this.name = 'ServiceError'
    this.service = service
    this.call = call
    this.kind = kind
    this.status = status
  }
}

export const TIMEOUTS = {
  health: 2_000,
  standard: 10_000,
  recording: 60_000,
  chat: 60_000,
  analyze: 300_000
} as const

export type CallOutcome = 'response' | 'offline'

type OutcomeListener = (service: ServiceName, outcome: CallOutcome) => void

const outcomeListeners = new Set<OutcomeListener>()

export function onCallOutcome(listener: OutcomeListener): () => void {
  outcomeListeners.add(listener)
  return () => {
    outcomeListeners.delete(listener)
  }
}

export interface CallRequest {
  service: ServiceName
  call: string
  path: string[]
  method?: 'GET' | 'POST'
  query?: Record<string, string | undefined>
  body?: unknown
  timeoutMs: number
  reportOutcome?: boolean
}

const MESSAGE_LIMIT = 200

function buildUrl(request: CallRequest): string {
  const path = request.path.map(encodeURIComponent).join('/')
  const query = Object.entries(request.query ?? {})
    .filter((entry): entry is [string, string] => entry[1] !== undefined)
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
    .join('&')
  return `${serviceUrl(request.service)}/${path}${query ? `?${query}` : ''}`
}

function report(request: CallRequest, outcome: CallOutcome): void {
  if (request.reportOutcome === false) return
  outcomeListeners.forEach((listener) => listener(request.service, outcome))
}

function networkFailure(request: CallRequest, signal: AbortSignal): ServiceError {
  if (signal.aborted) {
    return new ServiceError(
      request.service,
      request.call,
      'timeout',
      `${request.call} got no complete answer from ${request.service} within ${request.timeoutMs / 1000} s`
    )
  }
  report(request, 'offline')
  return new ServiceError(
    request.service,
    request.call,
    'offline',
    `${request.service} is not reachable at ${serviceUrl(request.service)}`
  )
}

export async function guardNetwork<T>(request: CallRequest, signal: AbortSignal, run: () => Promise<T>): Promise<T> {
  try {
    return await run()
  } catch {
    throw networkFailure(request, signal)
  }
}

function serverMessage(text: string): string {
  let message = text
  try {
    const body: unknown = JSON.parse(text)
    if (body !== null && typeof body === 'object' && 'detail' in body) {
      const detail = (body as { detail: unknown }).detail
      message = typeof detail === 'string' ? detail : JSON.stringify(detail)
    }
  } catch {
    message = text
  }
  return message.slice(0, MESSAGE_LIMIT)
}

async function statusFailure(request: CallRequest, response: Response): Promise<ServiceError> {
  const text = await response.text().catch(() => '')
  if (response.status === 404) {
    return new ServiceError(request.service, request.call, 'not_found', serverMessage(text) || 'Not found', 404)
  }
  return new ServiceError(
    request.service,
    request.call,
    'http',
    serverMessage(text) || `HTTP ${response.status}`,
    response.status
  )
}

export async function exchange<T>(
  request: CallRequest,
  read: (response: Response, signal: AbortSignal) => Promise<T>
): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), request.timeoutMs)
  const init: RequestInit = { method: request.method ?? 'GET', signal: controller.signal }
  if (request.body !== undefined) {
    init.body = JSON.stringify(request.body)
    init.headers = { 'Content-Type': 'application/json' }
  }
  try {
    const response = await guardNetwork(request, controller.signal, () => fetch(buildUrl(request), init))
    report(request, 'response')
    if (!response.ok) throw await statusFailure(request, response)
    return await read(response, controller.signal)
  } finally {
    clearTimeout(timer)
  }
}

export function requestJson<T>(request: CallRequest & { expect: 'object' | 'array' }): Promise<T> {
  return exchange(request, async (response, signal) => {
    const text = await guardNetwork(request, signal, () => response.text())
    let value: unknown
    try {
      value = JSON.parse(text)
    } catch {
      throw new ServiceError(request.service, request.call, 'bad_response', `${request.call} answered with something other than JSON`)
    }
    const kind = Array.isArray(value) ? 'array' : value !== null && typeof value === 'object' ? 'object' : 'other'
    if (kind !== request.expect) {
      throw new ServiceError(
        request.service,
        request.call,
        'bad_response',
        `${request.call} answered with JSON that is not an ${request.expect}`
      )
    }
    return value as T
  })
}
