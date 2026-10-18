import { app, BrowserWindow, globalShortcut, ipcMain, screen } from 'electron'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { INSIGHTS_CHANNEL, OVERLAY_CHANNEL, SERVICES_CHANNEL, TALK_CHANNEL, TALK_KEY_CHANNEL } from '../shared/bridge'
import { insightsEnabled, overlayMode, readAppEnv, resolveServiceAddresses, talkKey } from './services'
import { handleMicrophone, handleVoice, readVoiceSettings } from './voice'

const OVERLAY_DESIGN_WIDTH = 1920

const webPreferences = {
  preload: join(__dirname, '../preload/index.js'),
  contextIsolation: true,
  nodeIntegration: false,
  sandbox: true,
  autoplayPolicy: 'no-user-gesture-required' as const
}

let mainWindow: BrowserWindow | null = null

function isAppPage(url: string): boolean {
  if (!app.isPackaged && process.env.ELECTRON_RENDERER_URL) {
    return url.startsWith(`${process.env.ELECTRON_RENDERER_URL.replace(/\/+$/, '')}/`)
  }
  return url.startsWith(`${pathToFileURL(join(__dirname, '../renderer')).href}/`)
}

function loadPage(win: BrowserWindow, page: 'index.html' | 'overlay.html'): void {
  if (!app.isPackaged && process.env.ELECTRON_RENDERER_URL) {
    win.loadURL(`${process.env.ELECTRON_RENDERER_URL}/${page}`)
  } else {
    win.loadFile(join(__dirname, '../renderer', page))
  }
}

function createMainWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 640,
    title: 'Kumite',
    show: false,
    webPreferences: { ...webPreferences, backgroundThrottling: false }
  })
  win.once('ready-to-show', () => win.show())
  win.on('closed', () => {
    mainWindow = null
    if (process.platform !== 'darwin') app.quit()
  })
  loadPage(win, 'index.html')
  return win
}

function createOverlayWindow(): BrowserWindow {
  const { bounds } = screen.getPrimaryDisplay()
  const win = new BrowserWindow({
    x: bounds.x,
    y: bounds.y,
    width: bounds.width,
    height: bounds.height,
    frame: false,
    transparent: true,
    hasShadow: false,
    skipTaskbar: true,
    resizable: false,
    movable: false,
    focusable: false,
    alwaysOnTop: true,
    show: false,
    webPreferences
  })
  win.setAlwaysOnTop(true, 'screen-saver')
  win.setIgnoreMouseEvents(true)
  if (process.platform === 'darwin') win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
  win.webContents.on('did-finish-load', () => {
    win.webContents.setZoomFactor(bounds.width / OVERLAY_DESIGN_WIDTH)
  })
  win.once('ready-to-show', () => win.showInactive())
  loadPage(win, 'overlay.html')
  return win
}

app.whenReady().then(() => {
  const fileValues = readAppEnv()
  const services = resolveServiceAddresses(fileValues)
  const overlay = overlayMode(fileValues)
  ipcMain.on(SERVICES_CHANNEL, (event) => {
    event.returnValue = services
  })
  ipcMain.on(OVERLAY_CHANNEL, (event) => {
    event.returnValue = overlay === 'always' ? 'always' : 'demo'
  })
  const insights = insightsEnabled(fileValues)
  ipcMain.on(INSIGHTS_CHANNEL, (event) => {
    event.returnValue = insights
  })
  handleVoice(readVoiceSettings(fileValues))
  handleMicrophone(isAppPage)
  const wanted = talkKey(fileValues)
  let talk: string | null = null
  if (wanted !== null) {
    let registered = false
    try {
      registered = globalShortcut.register(wanted, () => mainWindow?.webContents.send(TALK_CHANNEL))
    } catch (error) {
      console.warn(`[kumite] talk key ${wanted} is not a valid accelerator (${(error as Error).message})`)
    }
    if (registered) talk = wanted
    else console.warn(`[kumite] could not register the talk key ${wanted}; talking to the coach from the game is off`)
  }
  ipcMain.on(TALK_KEY_CHANNEL, (event) => {
    event.returnValue = talk
  })
  mainWindow = createMainWindow()
  if (overlay !== 'off') createOverlayWindow()
  app.on('activate', () => {
    if (mainWindow === null) mainWindow = createMainWindow()
  })
})

app.on('will-quit', () => {
  globalShortcut.unregisterAll()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
