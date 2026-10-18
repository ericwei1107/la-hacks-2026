import type { KumiteApi } from '../shared/bridge'

declare global {
  interface Window {
    kumite?: KumiteApi
  }
}
