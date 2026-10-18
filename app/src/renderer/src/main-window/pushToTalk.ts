import { useSyncExternalStore } from 'react'

const STORAGE_KEY = 'kumite.pushToTalkKey'
const DEFAULT_KEY = 'V'
const listeners = new Set<() => void>()

function read(): string {
  try {
    return window.localStorage.getItem(STORAGE_KEY) ?? DEFAULT_KEY
  } catch {
    return DEFAULT_KEY
  }
}

let current = read()

export function setPushToTalkKey(key: string): void {
  current = key
  try {
    window.localStorage.setItem(STORAGE_KEY, key)
  } catch {
    current = key
  }
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function usePushToTalkKey(): string {
  return useSyncExternalStore(subscribe, () => current)
}

export function keyLabel(event: KeyboardEvent): string {
  if (event.code.startsWith('Key')) return event.code.slice(3)
  if (event.code.startsWith('Digit')) return event.code.slice(5)
  if (event.key === ' ') return 'Space'
  return event.key.length === 1 ? event.key.toUpperCase() : event.key
}
