import { useCallback, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react'
import type { TranscribeResult } from '../../shared/bridge'
import { useConfig, useLatestCoach, useRoundBreak, type RoundBreak } from './services'
import { Store } from './services/store'

const speaking = new Store(false)
let audio: HTMLAudioElement | null = null
let clipUrl: string | null = null
let request = 0

function release(): void {
  if (audio) {
    audio.onended = null
    audio.onerror = null
    audio.pause()
    audio = null
  }
  if (clipUrl) {
    URL.revokeObjectURL(clipUrl)
    clipUrl = null
  }
  if (speaking.get()) speaking.set(false)
}

export function stopSpeaking(): void {
  request += 1
  release()
}

async function play(text: string): Promise<void> {
  stopSpeaking()
  const id = request
  const bridge = window.kumite
  if (!bridge?.speak) return
  let result: Awaited<ReturnType<typeof bridge.speak>>
  try {
    result = await bridge.speak(text)
  } catch {
    return
  }
  if (id !== request || !result.ok) return
  clipUrl = URL.createObjectURL(new Blob([result.audio], { type: 'audio/mpeg' }))
  const clip = new Audio(clipUrl)
  audio = clip
  clip.onended = release
  clip.onerror = release
  clip.play().then(
    () => {
      if (id === request) speaking.set(true)
    },
    () => {
      if (id === request) release()
    }
  )
}

export function useVoice() {
  const config = useConfig()
  const enabled = config.data?.voice === true
  const isSpeaking = useSyncExternalStore(speaking.subscribe, speaking.get)

  useEffect(() => {
    if (!enabled) stopSpeaking()
  }, [enabled])

  const speak = useCallback((text: string) => {
    if (enabled) void play(text)
  }, [enabled])

  return { speaking: isSpeaking, speak, stop: stopSpeaking }
}

export function useBetweenRoundVoice(): void {
  const { roundBreak } = useRoundBreak()
  const coach = useLatestCoach()
  const { speak, stop } = useVoice()
  const spoken = useRef<RoundBreak | null>(null)
  const previous = useRef<RoundBreak | null>(null)
  const line = roundBreak && coach && coach.record.session_id === roundBreak.sessionId && coach.record.round === roundBreak.round
    ? coach.record.text
    : null

  useEffect(() => {
    if (roundBreak && line && spoken.current !== roundBreak) {
      spoken.current = roundBreak
      speak(line)
    }
  }, [roundBreak, line, speak])

  useEffect(() => {
    if (previous.current && !roundBreak) stop()
    previous.current = roundBreak
  }, [roundBreak, stop])
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
    stopSpeaking()
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
