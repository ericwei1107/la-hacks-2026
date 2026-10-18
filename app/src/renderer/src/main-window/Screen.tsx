import type { ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { OfflineBanner, Select, setTime } from '../design'
import { health, useServiceStatus, type ServiceName } from '../services'
import { useFrame } from './frame'

const SERVICE_PHRASES: Record<ServiceName, string> = {
  brain: 'the brain',
  replay: 'the replay service',
  analytics: 'analytics'
}

function SetPicker() {
  const { sessions, sessionsFailed, selectedId, select } = useFrame()
  if (!selectedId) return null
  if (sessionsFailed) {
    return (
      <Select aria-label="Set" value="saved" onChange={() => undefined}>
        <option value="saved">Last saved set</option>
      </Select>
    )
  }
  if (!sessions || sessions.length === 0) return null
  return (
    <Select aria-label="Set" value={selectedId} onChange={(event) => select(event.currentTarget.value)}>
      {sessions.map((session) => (
        <option key={session.session_id} value={session.session_id}>
          {setTime(session.started_at)} set
        </option>
      ))}
    </Select>
  )
}

export function useOfflineService(services: ServiceName[]): ServiceName | null {
  const brain = useServiceStatus('brain')
  const replay = useServiceStatus('replay')
  const analytics = useServiceStatus('analytics')
  const states: Record<ServiceName, string> = { brain: brain.state, replay: replay.state, analytics: analytics.state }
  return services.find((service) => states[service] === 'offline') ?? null
}

interface ScreenBannerProps {
  service: ServiceName | null
  line?: string
}

export function ScreenBanner({ service, line }: ScreenBannerProps) {
  const client = useQueryClient()
  if (!service) return null
  const retry = () => {
    void health(service).catch(() => undefined)
    void client.invalidateQueries({ queryKey: [service] })
  }
  return (
    <OfflineBanner
      headline={`Can't reach ${SERVICE_PHRASES[service]}.`}
      line={line ?? 'What you see is the last thing it sent. This screen catches up when it reconnects.'}
      onRetry={retry}
    />
  )
}

interface ScreenProps {
  title: string
  picker?: boolean
  gap?: string
  children: ReactNode
}

export function Screen({ title, picker = false, gap = 'gap-[36px]', children }: ScreenProps) {
  return (
    <main className={`flex min-h-full grow basis-0 flex-col px-[56px] pt-[36px] pb-[40px] ${gap}`}>
      <header className="flex items-end justify-between">
        <h1 className="font-display text-2xl leading-12 tracking-tight text-text">{title}</h1>
        {picker && <SetPicker />}
      </header>
      {children}
    </main>
  )
}
