import { SERVICE_NAMES, type ServiceAddress, type ServiceName } from '../../../shared/bridge'
import { addresses } from './addresses'
import type { Health } from './contracts'
import { onCallOutcome, requestJson, TIMEOUTS } from './http'
import { Channel, Store } from './store'

export type ServiceState = 'unknown' | 'online' | 'offline'

export interface ServiceStatus {
  state: ServiceState
  address: ServiceAddress
  checkedAt: number | null
  name: string | null
  version: string | null
}

const POLL_INTERVAL_MS = 5_000

export const serviceStatus = Object.fromEntries(
  SERVICE_NAMES.map((service) => [
    service,
    new Store<ServiceStatus>({ state: 'unknown', address: addresses[service], checkedAt: null, name: null, version: null })
  ])
) as Record<ServiceName, Store<ServiceStatus>>

export const servicesBackOnline = new Channel<ServiceName>()

function setState(service: ServiceName, state: Exclude<ServiceState, 'unknown'>, health?: Health): void {
  const store = serviceStatus[service]
  const previous = store.get()
  store.set({
    ...previous,
    state,
    checkedAt: Date.now(),
    ...(health ? { name: health.service, version: health.version } : {})
  })
  if (previous.state === 'offline' && state === 'online') servicesBackOnline.emit(service)
}

export async function health(service: ServiceName): Promise<Health> {
  let reply: Health
  try {
    reply = await requestJson<Health>({
      service,
      call: 'health',
      path: ['health'],
      timeoutMs: TIMEOUTS.health,
      expect: 'object',
      reportOutcome: false
    })
  } catch (error) {
    setState(service, 'offline')
    throw error
  }
  if (reply.ok === true) setState(service, 'online', reply)
  else setState(service, 'offline')
  return reply
}

onCallOutcome((service, outcome) => setState(service, outcome === 'offline' ? 'offline' : 'online'))

export function startHealthPolling(): () => void {
  const check = (): void => {
    SERVICE_NAMES.forEach((service) => {
      health(service).catch(() => undefined)
    })
  }
  check()
  const timer = setInterval(check, POLL_INTERVAL_MS)
  return () => clearInterval(timer)
}
