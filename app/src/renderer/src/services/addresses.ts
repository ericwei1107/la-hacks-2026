import {
  DEFAULT_SERVICE_URLS,
  SERVICE_NAMES,
  type ServiceAddresses,
  type ServiceName
} from '../../../shared/bridge'

function defaults(): ServiceAddresses {
  return Object.fromEntries(
    SERVICE_NAMES.map((service) => [service, { url: DEFAULT_SERVICE_URLS[service], source: 'default' }])
  ) as ServiceAddresses
}

export const addresses: ServiceAddresses = window.kumite?.services ?? defaults()

export function serviceUrl(service: ServiceName): string {
  return addresses[service].url
}

export function streamUrl(path: '/ws/state' | '/ws/coach'): string {
  return addresses.brain.url.replace(/^http/, 'ws') + path
}
