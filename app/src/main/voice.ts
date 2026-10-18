import { ipcMain } from 'electron'
import { SPEAK_CHANNEL, type SpeakResult } from '../shared/bridge'

const TTS_URL = 'https://api.elevenlabs.io/v1/text-to-speech'
const TTS_MODEL = 'eleven_flash_v2_5'
const TTS_FORMAT = 'mp3_44100_128'
const SPEAK_TIMEOUT_MS = 6_000

type EnvValues = Record<string, string | undefined>

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

function failure(error: unknown): SpeakResult {
  return { ok: false, reason: (error as Error).name === 'TimeoutError' ? 'timeout' : 'network' }
}

async function request(settings: VoiceSettings, text: string): Promise<SpeakResult> {
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

export async function speak(settings: VoiceSettings, text: string): Promise<SpeakResult> {
  const result = await request(settings, text)
  if (!result.ok && result.reason !== 'not_configured') {
    warn(`speech failed: ${result.reason}${result.status === undefined ? '' : ` (${result.status})`}`)
  }
  return result
}

export function handleVoice(settings: VoiceSettings): void {
  ipcMain.handle(SPEAK_CHANNEL, (_event, text: unknown) => speak(settings, typeof text === 'string' ? text : ''))
}
