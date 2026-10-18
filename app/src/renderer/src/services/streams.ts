import { streamUrl } from './addresses'
import type { CoachMessage, GameEvent, GameState, PlanRecord, RoundSummary } from './contracts'
import { Channel, Store } from './store'

export type StreamName = 'state' | 'coach'

export type StreamStatus = 'connecting' | 'open' | 'reconnecting'

export interface Slot<T> {
  record: T
  receivedAt: number
}

type StreamRecord = Record<string, unknown> & { t: string }

const FIRST_WAIT_MS = 500
const LONGEST_WAIT_MS = 5_000
const OPEN_TIMEOUT_MS = 3_000

class BrainStream {
  readonly status: Store<StreamStatus>
  private readonly path: '/ws/state' | '/ws/coach'
  private readonly handle: (record: StreamRecord) => void
  private started = false
  private opened = false
  private wait = FIRST_WAIT_MS

  constructor(path: '/ws/state' | '/ws/coach', handle: (record: StreamRecord) => void) {
    this.path = path
    this.handle = handle
    this.status = new Store<StreamStatus>('connecting', () => this.start())
  }

  start(): void {
    if (this.started) return
    this.started = true
    this.connect()
  }

  private connect(): void {
    let socket: WebSocket
    try {
      socket = new WebSocket(streamUrl(this.path))
    } catch {
      this.retry()
      return
    }
    let lost = false
    const onLost = (): void => {
      if (lost) return
      lost = true
      window.clearTimeout(timer)
      socket.close()
      this.retry()
    }
    const timer = window.setTimeout(() => {
      if (socket.readyState === WebSocket.CONNECTING) onLost()
    }, OPEN_TIMEOUT_MS)
    socket.onopen = () => {
      window.clearTimeout(timer)
      this.opened = true
      this.wait = FIRST_WAIT_MS
      this.status.set('open')
    }
    socket.onmessage = (message) => this.receive(message.data)
    socket.onerror = onLost
    socket.onclose = onLost
  }

  private retry(): void {
    if (this.opened) this.status.set('reconnecting')
    setTimeout(() => this.connect(), this.wait)
    this.wait = Math.min(this.wait * 2, LONGEST_WAIT_MS)
  }

  private receive(data: unknown): void {
    if (typeof data !== 'string') return
    let value: unknown
    try {
      value = JSON.parse(data)
    } catch {
      return
    }
    if (value === null || typeof value !== 'object' || Array.isArray(value)) return
    if (typeof (value as { t?: unknown }).t !== 'string') return
    this.handle(value as StreamRecord)
  }
}

function slot<T>(record: T): Slot<T> {
  return { record, receivedAt: Date.now() }
}

const stateStream: BrainStream = new BrainStream('/ws/state', (record) => {
  if (record.t === 'state') latestState.set(slot(record as unknown as GameState))
  else if (record.t === 'event') gameEvents.emit(record as unknown as GameEvent)
  else if (record.t === 'plan') latestPlan.set(slot(record as unknown as PlanRecord))
})

const coachStream: BrainStream = new BrainStream('/ws/coach', (record) => {
  if (record.t === 'coach') {
    const message = record as unknown as CoachMessage
    latestCoach.set(slot(message))
    coachMessages.emit(message)
  } else if (record.t === 'round_summary') {
    const summary = record as unknown as RoundSummary
    latestSummary.set(slot(summary))
    roundSummaries.emit(summary)
  }
})

export const streams: Record<StreamName, BrainStream> = { state: stateStream, coach: coachStream }

export const latestState = new Store<Slot<GameState> | null>(null, () => stateStream.start())
export const gameEvents = new Channel<GameEvent>(() => stateStream.start())
export const latestPlan = new Store<Slot<PlanRecord> | null>(null, () => stateStream.start())

export const latestCoach = new Store<Slot<CoachMessage> | null>(null, () => coachStream.start())
export const coachMessages = new Channel<CoachMessage>(() => coachStream.start())

export const latestSummary = new Store<Slot<RoundSummary> | null>(null, () => coachStream.start())
export const roundSummaries = new Channel<RoundSummary>(() => coachStream.start())
