export const SERVICE_NAMES = ['brain', 'replay', 'analytics'] as const

export type ServiceName = (typeof SERVICE_NAMES)[number]

export type AddressSource = 'env' | 'file' | 'default'

export interface ServiceAddress {
  url: string
  source: AddressSource
  warning?: string
}

export type ServiceAddresses = Record<ServiceName, ServiceAddress>

export interface KumiteApi {
  platform: string
  services: ServiceAddresses
}

export const DEFAULT_SERVICE_URLS: Record<ServiceName, string> = {
  brain: 'http://localhost:8765',
  replay: 'http://localhost:8766',
  analytics: 'http://localhost:8767'
}

export const SERVICES_CHANNEL = 'kumite:services'
