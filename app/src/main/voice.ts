import { ipcMain, session, systemPreferences } from 'electron'
import {
  SPEAK_CHANNEL,
  TRANSCRIBE_CHANNEL,
  type SpeakResult,
  type TranscribeResult,
  type VoiceFailure
} from '../shared/bridge'

const TTS_URL = 'https://api.elevenlabs.io/v1/text-to-speech'
const TTS_MODEL = 'eleven_flash_v2_5'
const TTS_FORMAT = 'mp3_44100_128'
const SPEAK_TIMEOUT_MS = 6_000
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

async function requestSpeech(settings: VoiceSettings, text: string): Promise<SpeakResult> {
  if (!settings.apiKey || !settings.voiceId) return { ok: false, reason: 'not_configured' }
  const url = `${TTS_URL}/${encodeURIComponent(settings.voiceId)}?output_format=${TTS_FORMAT}`
  let response: Response
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: { 'xi-api-key': settings.apiKey, 'Content-Type': 'application/json', Accept: 'audio/mpeg' },
      body: JSON.stringify({ text, model_id: TTS_MODEL }),
      signal: AbortSignal.timeout(SPEAK_TIMEOUT_MS)
    })
  } catch (error) {
    return failure(error)
  }
  if (!response.ok) return { ok: false, reason: 'rejected', status: response.status }
  try {
    return { ok: true, audio: new Uint8Array(await response.arrayBuffer()) }
  } catch (error) {
    return failure(error)
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

export async function speak(settings: VoiceSettings, text: string): Promise<SpeakResult> {
  return report('speech', await requestSpeech(settings, text))
}

export async function transcribe(settings: VoiceSettings, recording: Uint8Array<ArrayBuffer>, mimeType: string): Promise<TranscribeResult> {
  return report('transcription', await requestTranscript(settings, recording, mimeType))
}

export function handleVoice(settings: VoiceSettings): void {
  ipcMain.handle(SPEAK_CHANNEL, (_event, text: unknown) => speak(settings, typeof text === 'string' ? text : ''))
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
