import { useCallback, useEffect, useSyncExternalStore } from 'react'
import { useConfig } from './services'
import { Store } from './services/store'

const speaking = new Store(false)
let audio: HTMLAudioElement | null = null
let clipUrl: string | null = null
let request = 0

function release(): void {
  if (audio) {
    audio.onended = null
    audio.onerror = null
    audio.pause()
    audio = null
  }
  if (clipUrl) {
    URL.revokeObjectURL(clipUrl)
    clipUrl = null
  }
  if (speaking.get()) speaking.set(false)
}

export function stopSpeaking(): void {
  request += 1
  release()
}

async function play(text: string): Promise<void> {
  stopSpeaking()
  const id = request
  const bridge = window.kumite
  if (!bridge?.speak) return
  let result: Awaited<ReturnType<typeof bridge.speak>>
  try {
    result = await bridge.speak(text)
  } catch {
    return
  }
  if (id !== request || !result.ok) return
  clipUrl = URL.createObjectURL(new Blob([result.audio], { type: 'audio/mpeg' }))
  const clip = new Audio(clipUrl)
  audio = clip
  clip.onended = release
  clip.onerror = release
  clip.play().then(
    () => {
      if (id === request) speaking.set(true)
    },
    () => {
      if (id === request) release()
    }
  )
}

export function useVoice() {
  const config = useConfig()
  const enabled = config.data?.voice === true
  const isSpeaking = useSyncExternalStore(speaking.subscribe, speaking.get)

  useEffect(() => {
    if (!enabled) stopSpeaking()
  }, [enabled])

  const speak = useCallback((text: string) => {
    if (enabled) void play(text)
  }, [enabled])

  return { speaking: isSpeaking, speak, stop: stopSpeaking }
}
