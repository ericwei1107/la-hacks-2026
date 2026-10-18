import { ipcMain, session, systemPreferences, type WebContents } from 'electron'
import {
  SPEAK_CHANNEL,
  SPEAK_CHUNK_CHANNEL,
  TRANSCRIBE_CHANNEL,
  type SpeakResult,
  type TranscribeResult,
  type VoiceFailure
} from '../shared/bridge'

const TTS_URL = 'https://api.elevenlabs.io/v1/text-to-speech'
const VOICES_URL = 'https://api.elevenlabs.io/v1/voices'
const TTS_MODELS = ['eleven_flash_v2_5', 'eleven_turbo_v2_5']
const MODEL_REJECTED = new Set([400, 403, 404, 422])
const TTS_FORMAT = 'mp3_44100_128'
const TTS_SPEED = 1.15
const SPEAK_TIMEOUT_MS = 6_000
const VOICE_SETTINGS_TIMEOUT_MS = 3_000
const STT_URL = 'https://api.elevenlabs.io/v1/speech-to-text'
const STT_MODEL = 'scribe_v2'
const STT_LANGUAGE = 'en'
const TRANSCRIBE_TIMEOUT_MS = 10_000

type EnvValues = Record<string, string | undefined>

type Failure = { ok: false; reason: VoiceFailure; status?: number }

export interface VoiceSettings {
  apiKey: string | null
  voiceId: string | null
}

function warn(message: string): void {
  console.warn(`[kumite] ${message}`)
}

function setting(name: string, fileValues: EnvValues): string | null {
  return process.env[name]?.trim() || fileValues[name]?.trim() || null
}

export function readVoiceSettings(fileValues: EnvValues): VoiceSettings {
  const settings = {
    apiKey: setting('ELEVENLABS_API_KEY', fileValues),
    voiceId: setting('ELEVENLABS_VOICE_ID', fileValues)
  }
  const missing = [
    settings.apiKey ? null : 'ELEVENLABS_API_KEY',
    settings.voiceId ? null : 'ELEVENLABS_VOICE_ID'
  ].filter(Boolean)
  if (missing.length > 0) warn(`the coach will not speak: ${missing.join(' and ')} not set in the environment or app/.env`)
  return settings
}

function failure(error: unknown): Failure {
  return { ok: false, reason: (error as Error).name === 'TimeoutError' ? 'timeout' : 'network' }
}

function report<T extends { ok: boolean }>(call: string, result: T): T {
  const failed = result as unknown as Failure
  if (!result.ok && failed.reason !== 'not_configured') {
    warn(`${call} failed: ${failed.reason}${failed.status === undefined ? '' : ` (${failed.status})`}`)
  }
  return result
}

let modelIndex = 0
let storedVoiceSettings: Promise<Record<string, unknown>> | null = null

function voiceSettings(settings: VoiceSettings): Promise<Record<string, unknown>> {
  if (!settings.apiKey || !settings.voiceId) return Promise.resolve({})
  storedVoiceSettings ??= fetch(`${VOICES_URL}/${encodeURIComponent(settings.voiceId)}/settings`, {
    headers: { 'xi-api-key': settings.apiKey },
    signal: AbortSignal.timeout(VOICE_SETTINGS_TIMEOUT_MS)
  })
    .then(async (response) => {
      if (!response.ok) throw new Error(`status ${response.status}`)
      const body = (await response.json()) as unknown
      if (body === null || typeof body !== 'object' || Array.isArray(body)) return {}
      return Object.fromEntries(Object.entries(body).filter(([, value]) => value !== null && value !== undefined))
    })
    .catch((error: unknown) => {
      warn(`could not read the voice's stored settings (${(error as Error).message}); speaking with speed only`)
      return {}
    })
  return storedVoiceSettings
}

async function streamSpeech(settings: VoiceSettings, text: string, onChunk: (chunk: Uint8Array) => void): Promise<SpeakResult> {
  if (!settings.apiKey || !settings.voiceId) return { ok: false, reason: 'not_configured' }
  const url = `${TTS_URL}/${encodeURIComponent(settings.voiceId)}/stream?output_format=${TTS_FORMAT}`
  const voice_settings = { ...(await voiceSettings(settings)), speed: TTS_SPEED }
  for (;;) {
    const model = TTS_MODELS[modelIndex]
    const controller = new AbortController()
    let timedOut = false
    let timer: NodeJS.Timeout | undefined
    const arm = (): void => {
      clearTimeout(timer)
      timer = setTimeout(() => {
        timedOut = true
        controller.abort()
      }, SPEAK_TIMEOUT_MS)
    }
    const cut = (): Failure => ({ ok: false, reason: timedOut ? 'timeout' : 'network' })
    arm()
    try {
      let response: Response
      try {
        response = await fetch(url, {
          method: 'POST',
          headers: { 'xi-api-key': settings.apiKey, 'Content-Type': 'application/json', Accept: 'audio/mpeg' },
          body: JSON.stringify({ text, model_id: model, voice_settings }),
          signal: controller.signal
        })
      } catch {
        return cut()
      }
      if (!response.ok) {
        if (MODEL_REJECTED.has(response.status) && modelIndex < TTS_MODELS.length - 1) {
          modelIndex += 1
          warn(`ElevenLabs refused ${model} (${response.status}); speaking with ${TTS_MODELS[modelIndex]}`)
          continue
        }
        return { ok: false, reason: 'rejected', status: response.status }
      }
      if (!response.body) return { ok: false, reason: 'network' }
      const reader = response.body.getReader()
      try {
        for (;;) {
          arm()
          const { done, value } = await reader.read()
          if (done) return { ok: true }
          if (value && value.byteLength > 0) onChunk(value)
        }
      } catch {
        return cut()
      }
    } finally {
      clearTimeout(timer)
    }
  }
}

async function requestTranscript(settings: VoiceSettings, recording: Uint8Array<ArrayBuffer>, mimeType: string): Promise<TranscribeResult> {
  if (!settings.apiKey) return { ok: false, reason: 'not_configured' }
  const form = new FormData()
  form.append('model_id', STT_MODEL)
  form.append('language_code', STT_LANGUAGE)
  form.append('file', new Blob([recording], { type: mimeType || 'audio/webm' }), 'question.webm')
  let response: Response
  try {
    response = await fetch(STT_URL, {
      method: 'POST',
      headers: { 'xi-api-key': settings.apiKey },
      body: form,
      signal: AbortSignal.timeout(TRANSCRIBE_TIMEOUT_MS)
    })
  } catch (error) {
    return failure(error)
  }
  if (!response.ok) return { ok: false, reason: 'rejected', status: response.status }
  try {
    const body = (await response.json()) as { text?: unknown }
    return { ok: true, text: typeof body.text === 'string' ? body.text.trim() : '' }
  } catch (error) {
    return failure(error)
  }
}

export async function speak(settings: VoiceSettings, text: string, onChunk: (chunk: Uint8Array) => void): Promise<SpeakResult> {
  return report('speech', await streamSpeech(settings, text, onChunk))
}

function sendChunk(sender: WebContents, id: number, chunk: Uint8Array | null): void {
  if (!sender.isDestroyed()) sender.send(SPEAK_CHUNK_CHANNEL, id, chunk)
}

export async function transcribe(settings: VoiceSettings, recording: Uint8Array<ArrayBuffer>, mimeType: string): Promise<TranscribeResult> {
  return report('transcription', await requestTranscript(settings, recording, mimeType))
}

export function handleVoice(settings: VoiceSettings): void {
  void voiceSettings(settings)
  ipcMain.handle(SPEAK_CHANNEL, async (event, id: unknown, text: unknown) => {
    const stream = typeof id === 'number' ? id : -1
    try {
      return await speak(settings, typeof text === 'string' ? text : '', (chunk) => sendChunk(event.sender, stream, chunk))
    } finally {
      sendChunk(event.sender, stream, null)
    }
  })
  ipcMain.handle(TRANSCRIBE_CHANNEL, (_event, recording: unknown, mimeType: unknown) =>
    transcribe(
      settings,
      recording instanceof Uint8Array ? new Uint8Array(recording) : new Uint8Array(),
      typeof mimeType === 'string' ? mimeType : ''
    )
  )
}

export function handleMicrophone(isAppPage: (url: string) => boolean): void {
  session.defaultSession.setPermissionRequestHandler((contents, permission, callback, details) => {
    if (permission !== 'media') {
      callback(true)
      return
    }
    const types = 'mediaTypes' in details ? (details.mediaTypes ?? []) : []
    const audioOnly = types.length > 0 && types.every((type) => type === 'audio')
    if (!audioOnly || !isAppPage(contents.getURL())) {
      callback(false)
      return
    }
    if (process.platform !== 'darwin') {
      callback(true)
      return
    }
    systemPreferences.askForMediaAccess('microphone').then(callback, () => callback(false))
  })
}
