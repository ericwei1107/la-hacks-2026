import type { Config, ConfigUpdate, Profile, SessionMeta } from './contracts'
import { requestJson, TIMEOUTS } from './http'

export function listSessions(): Promise<SessionMeta[]> {
  return requestJson({ service: 'brain', call: 'listSessions', path: ['sessions'], timeoutMs: TIMEOUTS.standard, expect: 'array' })
}

export function getSession(sessionId: string): Promise<SessionMeta> {
  return requestJson({
    service: 'brain',
    call: 'getSession',
    path: ['sessions', sessionId],
    timeoutMs: TIMEOUTS.standard,
    expect: 'object'
  })
}

export function getProfiles(player: string): Promise<Profile[]> {
  return requestJson({
    service: 'brain',
    call: 'getProfiles',
    path: ['profiles', player],
    timeoutMs: TIMEOUTS.standard,
    expect: 'array'
  })
}

export function getConfig(): Promise<Config> {
  return requestJson({ service: 'brain', call: 'getConfig', path: ['config'], timeoutMs: TIMEOUTS.standard, expect: 'object' })
}

export function postConfig(update: ConfigUpdate): Promise<Config> {
  return requestJson({
    service: 'brain',
    call: 'postConfig',
    path: ['config'],
    method: 'POST',
    body: update,
    timeoutMs: TIMEOUTS.standard,
    expect: 'object'
  })
}
