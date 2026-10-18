import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { parseEnv } from 'node:util'
import { app } from 'electron'
import {
  DEFAULT_SERVICE_URLS,
  SERVICE_NAMES,
  type AddressSource,
  type ServiceAddress,
  type ServiceAddresses,
  type ServiceName
} from '../shared/bridge'

const VARIABLES: Record<ServiceName, string> = {
  brain: 'KUMITE_BRAIN_URL',
  replay: 'KUMITE_REPLAY_URL',
  analytics: 'KUMITE_ANALYTICS_URL'
}

type EnvValues = Record<string, string | undefined>

interface Source {
  source: Exclude<AddressSource, 'default'>
  label: string
  values: EnvValues
}

function warn(message: string): void {
  console.warn(`[kumite] ${message}`)
}

export function readAppEnv(): EnvValues {
  const path = join(app.getAppPath(), '.env')
  let text: string
  try {
    text = readFileSync(path, 'utf8')
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
      warn(`could not read ${path} (${(error as Error).message}); resolving settings without it`)
    }
    return {}
  }
  try {
    return parseEnv(text)
  } catch (error) {
    warn(`could not parse ${path} (${(error as Error).message}); resolving settings without it`)
    return {}
  }
}

function acceptable(value: string): string | null {
  let url: URL
  try {
    url = new URL(value)
  } catch {
    return null
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return null
  return value.replace(/\/+$/, '')
}

function resolveOne(service: ServiceName, sources: Source[]): ServiceAddress {
  const variable = VARIABLES[service]
  const warnings: string[] = []
  const withWarning = (address: ServiceAddress): ServiceAddress =>
    warnings.length > 0 ? { ...address, warning: warnings.join(' ') } : address

  for (const { source, label, values } of sources) {
    const raw = values[variable]?.trim()
    if (!raw) continue
    const url = acceptable(raw)
    if (url) return withWarning({ url, source })
    const warning = `${variable} in ${label} is not an http(s) URL: "${raw}".`
    warn(warning)
    warnings.push(warning)
  }
  return withWarning({ url: DEFAULT_SERVICE_URLS[service], source: 'default' })
}

export function resolveServiceAddresses(fileValues: EnvValues): ServiceAddresses {
  const sources: Source[] = [
    { source: 'env', label: 'the environment', values: process.env },
    { source: 'file', label: 'app/.env', values: fileValues }
  ]
  return Object.fromEntries(
    SERVICE_NAMES.map((service) => [service, resolveOne(service, sources)])
  ) as ServiceAddresses
}

export function overlayMode(fileValues: EnvValues): 'always' | 'demo' | 'off' {
  const raw = (process.env.KUMITE_OVERLAY?.trim() || fileValues.KUMITE_OVERLAY?.trim() || '').toLowerCase()
  if (raw === '1' || raw === 'on') return 'always'
  if (raw === '0' || raw === 'off') return 'off'
  return 'demo'
}

export function insightsEnabled(fileValues: EnvValues): boolean {
  const raw = (process.env.KUMITE_INSIGHTS?.trim() || fileValues.KUMITE_INSIGHTS?.trim() || '').toLowerCase()
  return raw === '1' || raw === 'on'
}
