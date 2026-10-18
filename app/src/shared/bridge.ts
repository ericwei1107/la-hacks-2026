export const SERVICE_NAMES = ['brain', 'replay', 'analytics'] as const

export type ServiceName = (typeof SERVICE_NAMES)[number]

export type AddressSource = 'env' | 'file' | 'default'

export interface ServiceAddress {
  url: string
  source: AddressSource
  warning?: string
}

export type ServiceAddresses = Record<ServiceName, ServiceAddress>

export type VoiceFailure = 'not_configured' | 'rejected' | 'network' | 'timeout'

export type SpeakResult =
  | { ok: true; audio: Uint8Array<ArrayBuffer> }
  | { ok: false; reason: VoiceFailure; status?: number }

export type TranscribeResult =
  | { ok: true; text: string }
  | { ok: false; reason: VoiceFailure; status?: number }

export type OverlayMode = 'always' | 'demo'

export interface KumiteApi {
  platform: string
  services: ServiceAddresses
  overlay: OverlayMode
  insights: boolean
  speak: (text: string) => Promise<SpeakResult>
  transcribe: (recording: Uint8Array<ArrayBuffer>, mimeType: string) => Promise<TranscribeResult>
}

export const DEFAULT_SERVICE_URLS: Record<ServiceName, string> = {
  brain: 'http://localhost:8765',
  replay: 'http://localhost:8766',
  analytics: 'http://localhost:8767'
}

export const SERVICES_CHANNEL = 'kumite:services'

export const OVERLAY_CHANNEL = 'kumite:overlay'

export const INSIGHTS_CHANNEL = 'kumite:insights'

export const SPEAK_CHANNEL = 'kumite:speak'

export const TRANSCRIBE_CHANNEL = 'kumite:transcribe'
