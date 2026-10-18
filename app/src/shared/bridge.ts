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

export interface KumiteApi {
  platform: string
  services: ServiceAddresses
  speak: (text: string) => Promise<SpeakResult>
}

export const DEFAULT_SERVICE_URLS: Record<ServiceName, string> = {
  brain: 'http://localhost:8765',
  replay: 'http://localhost:8766',
  analytics: 'http://localhost:8767'
}

export const SERVICES_CHANNEL = 'kumite:services'

export const SPEAK_CHANNEL = 'kumite:speak'
