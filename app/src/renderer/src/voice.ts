import { useCallback, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react'
import type { TranscribeResult } from '../../shared/bridge'
import { useCoachListener, useConfig } from './services'
import { Store } from './services/store'

const STREAM_TYPE = 'audio/mpeg'
const ROUND_TAG = 'round'

interface Line {
  text: string
  tag: string
  chunks: Uint8Array[]
  done: boolean
  wake: () => void
}

const speaking = new Store<string | null>(null)
const queue: Line[] = []
let current: Line | null = null

function fetchLine(line: Line): void {
  const bridge = window.kumite
  const finish = (): void => {
    line.done = true
    line.wake()
  }
  if (!bridge?.speak) {
    finish()
    return
  }
  bridge
    .speak(line.text, (chunk) => {
      line.chunks.push(chunk)
      line.wake()
    })
    .then(finish, finish)
}

function changed(line: Line): Promise<void> {
  return new Promise((resolve) => {
    line.wake = () => {
      line.wake = () => {}
      resolve()
    }
  })
}

async function feed(line: Line, source: MediaSource, buffer: SourceBuffer): Promise<void> {
  let next = 0
  for (;;) {
    if (source.readyState !== 'open') return
    if (next < line.chunks.length) {
      const chunk = line.chunks[next]
      next += 1
      const appended = new Promise<void>((resolve) => buffer.addEventListener('updateend', () => resolve(), { once: true }))
      try {
        buffer.appendBuffer(new Uint8Array(chunk))
      } catch {
        if (source.readyState === 'open' && !buffer.updating) source.endOfStream()
        return
      }
      await appended
    } else if (line.done) {
      if (!buffer.updating) source.endOfStream()
      return
    } else {
      await changed(line)
    }
  }
}

function streamClip(line: Line): string {
  const source = new MediaSource()
  source.addEventListener(
    'sourceopen',
    () => {
      let buffer: SourceBuffer
      try {
        buffer = source.addSourceBuffer(STREAM_TYPE)
      } catch {
        source.endOfStream('decode')
        return
      }
      void feed(line, source, buffer)
    },
    { once: true }
  )
  return URL.createObjectURL(source)
}

async function wholeClip(line: Line): Promise<string> {
  while (!line.done) await changed(line)
  const parts = line.chunks.map((chunk) => new Uint8Array(chunk))
  return URL.createObjectURL(new Blob(parts, { type: STREAM_TYPE }))
}

async function playLine(line: Line): Promise<void> {
  while (line.chunks.length === 0 && !line.done) await changed(line)
  if (line.chunks.length === 0) return
  const url = MediaSource.isTypeSupported(STREAM_TYPE) ? streamClip(line) : await wholeClip(line)
  const clip = new Audio()
  try {
    await new Promise<void>((resolve) => {
      clip.onplaying = () => speaking.set(line.tag)
      clip.onended = () => resolve()
      clip.onerror = () => resolve()
      clip.src = url
      clip.play().catch(() => resolve())
    })
  } finally {
    clip.onplaying = null
    clip.onended = null
    clip.onerror = null
    URL.revokeObjectURL(url)
  }
}

function advance(): void {
  if (current) return
  const line = queue.shift()
  if (!line) return
  current = line
  playLine(line)
    .catch(() => {})
    .finally(() => {
      current = null
      speaking.set(null)
      advance()
    })
}

function enqueue(text: string, tag: string): void {
  if (!text.trim()) return
  const line: Line = { text, tag, chunks: [], done: false, wake: () => {} }
  queue.push(line)
  fetchLine(line)
  advance()
}

function dropQueuedLines(): void {
  queue.length = 0
}

export function useVoice() {
  const config = useConfig()
  const enabled = config.data?.voice === true
  const playing = useSyncExternalStore(speaking.subscribe, speaking.get)

  useEffect(() => {
    if (!enabled) dropQueuedLines()
  }, [enabled])

  const speak = useCallback((text: string, tag: string) => {
    if (enabled) enqueue(text, tag)
  }, [enabled])

  return { speaking: playing !== null, speakingTag: playing, speak }
}

export function useCoachRecordVoice(): void {
  const { speak } = useVoice()
  useCoachListener((message) => speak(message.text, ROUND_TAG))
}

const MIN_RECORDING_MS = 300
const MAX_RECORDING_MS = 30_000
const MIC_OFF = 'Microphone access is off. Allow it in System Settings → Privacy & Security → Microphone.'
const NOT_HEARD = "Didn't catch that. Hold the key and try again."

export type TalkPhase = 'idle' | 'listening' | 'transcribing'

interface Recording {
  stream: MediaStream | null
  recorder: MediaRecorder | null
  chunks: Blob[]
  startedAt: number
  released: boolean
  timer: number
}

function failureText(result: Exclude<TranscribeResult, { ok: true }>): string {
  if (result.reason === 'not_configured') return "Voice isn't set up on this machine."
  if (result.reason === 'rejected') return `ElevenLabs refused the request (${result.status}).`
  if (result.reason === 'timeout') return 'ElevenLabs took too long.'
  return "Can't reach ElevenLabs."
}

function microphoneText(error: unknown): string {
  const name = (error as Error).name
  if (name === 'NotAllowedError' || name === 'SecurityError') return MIC_OFF
  if (name === 'NotFoundError') return 'No microphone found.'
  return 'The microphone could not start.'
}

export function useHoldToTalk(onText: (text: string) => void, available: boolean) {
  const [phase, setPhase] = useState<TalkPhase>('idle')
  const [note, setNote] = useState<string | null>(null)
  const current = useRef<Recording | null>(null)
  const transcribing = useRef(false)
  const mounted = useRef(true)
  const deliver = useRef(onText)

  useLayoutEffect(() => {
    deliver.current = onText
  })

  const complete = useCallback(async (recording: Recording) => {
    window.clearTimeout(recording.timer)
    recording.stream?.getTracks().forEach((track) => track.stop())
    if (current.current === recording) current.current = null
    if (!mounted.current) return
    if (Date.now() - recording.startedAt < MIN_RECORDING_MS) {
      setPhase('idle')
      return
    }
    const bridge = window.kumite
    if (!bridge?.transcribe) {
      setPhase('idle')
      return
    }
    transcribing.current = true
    setPhase('transcribing')
    const clip = new Blob(recording.chunks, { type: recording.recorder?.mimeType || 'audio/webm' })
    let result: TranscribeResult
    try {
      result = await bridge.transcribe(new Uint8Array(await clip.arrayBuffer()), clip.type)
    } catch {
      result = { ok: false, reason: 'network' }
    }
    transcribing.current = false
    if (!mounted.current) return
    setPhase('idle')
    if (!result.ok) setNote(`Couldn't hear you. ${failureText(result)}`)
    else if (!result.text) setNote(NOT_HEARD)
    else deliver.current(result.text)
  }, [])

  const stop = useCallback(() => {
    const recording = current.current
    if (!recording || recording.released) return
    recording.released = true
    if (recording.recorder && recording.recorder.state !== 'inactive') recording.recorder.stop()
  }, [])

  const start = useCallback(async () => {
    if (!available || current.current || transcribing.current) return
    setNote(null)
    const recording: Recording = { stream: null, recorder: null, chunks: [], startedAt: 0, released: false, timer: 0 }
    current.current = recording
    setPhase('listening')
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (error) {
      if (current.current === recording) current.current = null
      if (mounted.current) {
        setPhase('idle')
        setNote(`Couldn't hear you. ${microphoneText(error)}`)
      }
      return
    }
    if (!mounted.current || recording.released || current.current !== recording) {
      stream.getTracks().forEach((track) => track.stop())
      if (current.current === recording) current.current = null
      if (mounted.current) setPhase('idle')
      return
    }
    const recorder = new MediaRecorder(stream)
    recording.stream = stream
    recording.recorder = recorder
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) recording.chunks.push(event.data)
    }
    recorder.onstop = () => void complete(recording)
    recorder.start()
    recording.startedAt = Date.now()
    recording.timer = window.setTimeout(stop, MAX_RECORDING_MS)
  }, [available, complete, stop])

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      const recording = current.current
      if (recording) {
        recording.released = true
        if (recording.recorder && recording.recorder.state !== 'inactive') recording.recorder.stop()
        else recording.stream?.getTracks().forEach((track) => track.stop())
      }
    }
  }, [])

  const clearNote = useCallback(() => setNote(null), [])

  return { phase, note, start, stop, clearNote }
}
