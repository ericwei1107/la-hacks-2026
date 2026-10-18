import { contextBridge, ipcRenderer } from 'electron'
import { SERVICES_CHANNEL, SPEAK_CHANNEL, type KumiteApi } from '../shared/bridge'

const api: KumiteApi = {
  platform: process.platform,
  services: ipcRenderer.sendSync(SERVICES_CHANNEL),
  speak: (text) => ipcRenderer.invoke(SPEAK_CHANNEL, text)
}

contextBridge.exposeInMainWorld('kumite', api)
