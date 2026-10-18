import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'
import {
  INSIGHTS_CHANNEL,
  OVERLAY_CHANNEL,
  SERVICES_CHANNEL,
  SPEAK_CHANNEL,
  SPEAK_CHUNK_CHANNEL,
  TRANSCRIBE_CHANNEL,
  type KumiteApi,
  type SpeakResult
} from '../shared/bridge'

let nextStream = 0

function speak(text: string, onChunk: (chunk: Uint8Array) => void): Promise<SpeakResult> {
  const id = nextStream++
  let finished: () => void = () => {}
  const ended = new Promise<void>((resolve) => {
    finished = resolve
  })
  const listener = (_event: IpcRendererEvent, stream: number, chunk: Uint8Array | null): void => {
    if (stream !== id) return
    if (chunk === null) {
      ipcRenderer.removeListener(SPEAK_CHUNK_CHANNEL, listener)
      finished()
    } else onChunk(chunk)
  }
  ipcRenderer.on(SPEAK_CHUNK_CHANNEL, listener)
  const result = ipcRenderer.invoke(SPEAK_CHANNEL, id, text) as Promise<SpeakResult>
  return result.then(
    async (value) => {
      await ended
      return value
    },
    (error: unknown) => {
      ipcRenderer.removeListener(SPEAK_CHUNK_CHANNEL, listener)
      throw error
    }
  )
}

const api: KumiteApi = {
  platform: process.platform,
  services: ipcRenderer.sendSync(SERVICES_CHANNEL),
  overlay: ipcRenderer.sendSync(OVERLAY_CHANNEL),
  insights: ipcRenderer.sendSync(INSIGHTS_CHANNEL),
  speak,
  transcribe: (recording, mimeType) => ipcRenderer.invoke(TRANSCRIBE_CHANNEL, recording, mimeType)
}

contextBridge.exposeInMainWorld('kumite', api)
