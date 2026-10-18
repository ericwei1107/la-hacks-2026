import type { GameEvent, GameState, PlanRecord, RoundSummary, TacticalRecord } from './contracts'
import { exchange, guardNetwork, TIMEOUTS, type CallRequest } from './http'

export interface Recording {
  sessionId: string
  events: GameEvent[]
  roundSummaries: RoundSummary[]
  plans: PlanRecord[]
  tactical: TacticalRecord[]
  states?: GameState[]
  skippedLines: number
}

export interface RecordingOptions {
  states?: boolean
}

function collect(recording: Recording, line: string): void {
  const text = line.trim()
  if (!text) return
  let record: unknown
  try {
    record = JSON.parse(text)
  } catch {
    recording.skippedLines += 1
    return
  }
  if (record === null || typeof record !== 'object' || Array.isArray(record)) {
    recording.skippedLines += 1
    return
  }
  switch ((record as { t?: unknown }).t) {
    case 'state':
      recording.states?.push(record as GameState)
      break
    case 'event':
      recording.events.push(record as GameEvent)
      break
    case 'round_summary':
      recording.roundSummaries.push(record as RoundSummary)
      break
    case 'plan':
      recording.plans.push(record as PlanRecord)
      break
    case 'tactical':
      recording.tactical.push(record as TacticalRecord)
      break
  }
}

export function getRecording(sessionId: string, options: RecordingOptions = {}): Promise<Recording> {
  const request: CallRequest = {
    service: 'brain',
    call: 'getRecording',
    path: ['sessions', sessionId, 'recording'],
    timeoutMs: TIMEOUTS.recording
  }
  return exchange(request, async (response, signal) => {
    const recording: Recording = {
      sessionId,
      events: [],
      roundSummaries: [],
      plans: [],
      tactical: [],
      ...(options.states ? { states: [] } : {}),
      skippedLines: 0
    }
    if (!response.body) return recording
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
    let partial = ''
    for (;;) {
      const { value, done } = await guardNetwork(request, signal, () => reader.read())
      if (done) break
      const lines = (partial + value).split('\n')
      partial = lines.pop() ?? ''
      lines.forEach((line) => collect(recording, line))
    }
    collect(recording, partial)
    return recording
  })
}
