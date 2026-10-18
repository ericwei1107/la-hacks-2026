import { contextBridge, ipcRenderer } from 'electron'
import { SERVICES_CHANNEL, SPEAK_CHANNEL, TRANSCRIBE_CHANNEL, type KumiteApi } from '../shared/bridge'

const api: KumiteApi = {
  platform: process.platform,
  services: ipcRenderer.sendSync(SERVICES_CHANNEL),
  speak: (text) => ipcRenderer.invoke(SPEAK_CHANNEL, text),
  transcribe: (recording, mimeType) => ipcRenderer.invoke(TRANSCRIBE_CHANNEL, recording, mimeType)
}

contextBridge.exposeInMainWorld('kumite', api)
