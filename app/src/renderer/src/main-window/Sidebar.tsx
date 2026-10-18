import { NavIcon, StatusDot, Wordmark, type NavIconName } from '../design'
import { useServiceStatus, type ServiceName } from '../services'
import { useFrame, type ScreenName } from './frame'

const NAV: { screen: ScreenName; label: string; icon: NavIconName }[] = [
  { screen: 'sessions', label: 'Sessions', icon: 'sessions' },
  { screen: 'replay', label: 'Replay analysis', icon: 'replay' },
  { screen: 'learning', label: 'Learning', icon: 'learning' },
  { screen: 'stats', label: 'Stats', icon: 'stats' },
  { screen: 'coach', label: 'Coach', icon: 'coach' },
  { screen: 'controls', label: 'Controls', icon: 'controls' }
]

const SERVICE_LABELS: Record<ServiceName, string> = { brain: 'Brain', replay: 'Replay', analytics: 'Analytics' }

function ServiceRow({ service }: { service: ServiceName }) {
  const status = useServiceStatus(service)
  const offline = status.state === 'offline'
  return (
    <div className="flex items-center gap-[10px]" title={status.address.warning ?? status.address.url}>
      <StatusDot state={status.state} />
      <span className={`text-sm leading-[18px] text-overlay-text ${offline ? 'font-bold' : 'font-medium'}`}>
        {offline ? `${SERVICE_LABELS[service]} offline` : SERVICE_LABELS[service]}
      </span>
    </div>
  )
}

export function Sidebar() {
  const { screen, open } = useFrame()
  return (
    <nav className="flex h-full w-sidebar shrink-0 flex-col justify-between bg-primary px-4 pt-8 pb-[28px]">
      <div className="flex flex-col gap-[40px]">
        <div className="flex items-center gap-3 px-[10px]">
          <Wordmark />
          <span className="font-display text-[26px] leading-8 tracking-tight text-overlay-text">Kumite</span>
        </div>
        <div className="flex flex-col gap-1">
          {NAV.map((item) => {
            const current = item.screen === screen
            return (
              <button
                key={item.screen}
                type="button"
                aria-current={current ? 'page' : undefined}
                onClick={() => open(item.screen)}
                className={`focus-ring flex h-[44px] shrink-0 items-center gap-3 rounded-sm px-3 text-left text-base/sm transition-colors duration-150 ${
                  current ? 'bg-bg font-bold text-primary' : 'font-medium text-overlay-muted hover:text-overlay-text'
                }`}
              >
                <NavIcon name={item.icon} color={current ? '#26365C' : '#A7A49E'} />
                {item.label}
              </button>
            )
          })}
        </div>
      </div>
      <div className="flex flex-col gap-[10px] border-t border-solid border-t-[#FFFFFF14] px-3 pt-4">
        <ServiceRow service="brain" />
        <ServiceRow service="replay" />
        <ServiceRow service="analytics" />
      </div>
    </nav>
  )
}
