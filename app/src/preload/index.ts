import { contextBridge, ipcRenderer } from 'electron'
import { SERVICES_CHANNEL, type KumiteApi } from '../shared/bridge'

const api: KumiteApi = {
  platform: process.platform,
  services: ipcRenderer.sendSync(SERVICES_CHANNEL)
}

contextBridge.exposeInMainWorld('kumite', api)
