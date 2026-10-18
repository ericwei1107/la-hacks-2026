import { useSyncExternalStore } from 'react'
import { Store } from '../services/store'

interface TalkRequest {
  seq: number
  consumed: boolean
}

const requests = new Store<TalkRequest>({ seq: 0, consumed: true })

export function requestTalk(): void {
  requests.set({ seq: requests.get().seq + 1, consumed: false })
}

export function consumeTalkRequest(): boolean {
  const request = requests.get()
  if (request.consumed) return false
  request.consumed = true
  return true
}

export function useTalkRequest(): number {
  return useSyncExternalStore(requests.subscribe, () => requests.get().seq)
}

export function talkKey(): string | null {
  return window.kumite?.talkKey ?? null
}
