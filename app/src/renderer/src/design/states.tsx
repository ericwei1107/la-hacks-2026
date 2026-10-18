import type { ReactNode } from 'react'
import type { ServiceState } from '../services'
import { Button } from './controls'
import { MatIllustration, Unlinked } from './icons'

export function StatusDot({ state }: { state: ServiceState }) {
  if (state === 'offline') return <span className="size-[10px] shrink-0 rounded-[5px] border-2 border-solid border-overlay-muted" />
  return <span className={`size-[10px] shrink-0 rounded-[5px] ${state === 'online' ? 'bg-ok' : 'bg-track'}`} />
}

export function Skeleton({ className = '', faint = false }: { className?: string; faint?: boolean }) {
  return <div className={`shrink-0 rounded-[4px] ${faint ? 'bg-[#CFC8A080]' : 'bg-[#CFC8A0BF]'} ${className}`} />
}

interface EmptyStateProps {
  headline: string
  line: string
  status?: { text: string; online: boolean }
  children?: ReactNode
}

export function EmptyState({ headline, line, status, children }: EmptyStateProps) {
  return (
    <div className="flex grow basis-0 flex-col justify-center gap-[28px] pb-[96px]">
      <MatIllustration />
      <div className="flex max-w-[520px] flex-col gap-[10px]">
        <h2 className="text-[32px] leading-[40px] font-[900] text-text">{headline}</h2>
        <p className="text-lg leading-[30px] text-text">{line}</p>
      </div>
      {children}
      {status && (
        <div className="flex items-center gap-[10px]">
          {status.online ? (
            <span className="size-[10px] shrink-0 rounded-[5px] bg-belt-green" />
          ) : (
            <span className="size-[10px] shrink-0 rounded-[5px] border-2 border-solid border-text-muted" />
          )}
          <span className="text-base/sm font-medium text-text-muted">{status.text}</span>
        </div>
      )}
    </div>
  )
}

interface OfflineBannerProps {
  headline: string
  line: string
  onRetry: () => void
}

export function OfflineBanner({ headline, line, onRetry }: OfflineBannerProps) {
  return (
    <div
      role="status"
      className="flex items-center gap-4 rounded-md border-2 border-solid border-primary bg-surface py-[10px] pr-[10px] pl-[18px]"
    >
      <Unlinked />
      <p className="flex grow basis-0 flex-wrap items-baseline gap-x-[6px] text-base/sm text-text">
        <span className="font-bold">{headline}</span>
        <span>{line}</span>
      </p>
      <Button onClick={onRetry}>Try again</Button>
    </div>
  )
}
