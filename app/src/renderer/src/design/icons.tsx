export type NavIconName = 'sessions' | 'replay' | 'learning' | 'stats' | 'coach' | 'controls'

export function NavIcon({ name, color }: { name: NavIconName; color: string }) {
  const line = { fill: 'none', stroke: color, strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true" className="shrink-0">
      {name === 'sessions' && (
        <>
          <path d="M7 5h10M7 10h10M7 15h10" {...line} />
          <circle cx="3.5" cy="5" r="0.9" fill={color} stroke={color} strokeWidth="1.75" />
          <circle cx="3.5" cy="10" r="0.9" fill={color} stroke={color} strokeWidth="1.75" />
          <circle cx="3.5" cy="15" r="0.9" fill={color} stroke={color} strokeWidth="1.75" />
        </>
      )}
      {name === 'replay' && (
        <>
          <path d="M3 4v12" {...line} />
          <path d="M7 4l10 6-10 6z" {...line} />
        </>
      )}
      {name === 'learning' && (
        <>
          <rect x="1.5" y="8" width="17" height="4" rx="1" {...line} />
          <rect x="7.5" y="5.5" width="5" height="9" rx="1.5" {...line} />
        </>
      )}
      {name === 'stats' && <path d="M4 17V11M10 17V3M16 17V8" {...line} />}
      {name === 'coach' && <path d="M2.5 3.5h15v10H8l-4.5 3.5v-3.5h-1z" {...line} />}
      {name === 'controls' && (
        <>
          <path d="M2 6h3M9 6h9M2 14h9M15 14h3" {...line} />
          <circle cx="7" cy="6" r="2.25" {...line} />
          <circle cx="13" cy="14" r="2.25" {...line} />
        </>
      )}
    </svg>
  )
}

export function Wordmark() {
  return (
    <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true" className="shrink-0">
      <rect x="1" y="1" width="18" height="8" fill="none" stroke="#F3F1ED" strokeWidth="2" />
      <rect x="21" y="1" width="8" height="18" fill="none" stroke="#F3F1ED" strokeWidth="2" />
      <rect x="11" y="21" width="18" height="8" fill="none" stroke="#F3F1ED" strokeWidth="2" />
      <rect x="1" y="11" width="8" height="18" fill="none" stroke="#F3F1ED" strokeWidth="2" />
      <rect x="11" y="11" width="8" height="8" fill="#E8C233" />
    </svg>
  )
}

export function Chevron({ color = 'var(--color-primary)' }: { color?: string }) {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" className="shrink-0">
      <path d="M2.5 4.5L6 8l3.5-3.5" fill="none" stroke={color} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function RowChevron({ open }: { open: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" className={`shrink-0 transition-transform duration-150 ${open ? 'rotate-180' : ''}`}>
      <path d="M4 6l4 4 4-4" fill="none" stroke="var(--color-text-muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function ArrowRight({ color = 'var(--color-overlay-text)', size = 14 }: { color?: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" aria-hidden="true" className="shrink-0">
      <path d="M2 7h10M8 3l4 4-4 4" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function SendArrow() {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true" className="shrink-0">
      <path d="M3 11h15M12 5l6 6-6 6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function PlayMark() {
  return (
    <svg width="10" height="12" viewBox="0 0 10 12" aria-hidden="true" className="shrink-0">
      <path d="M1 1L9 6L1 11Z" fill="var(--color-primary)" />
    </svg>
  )
}

export function Check() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" className="shrink-0">
      <path d="M3 8.5l3.5 3.5L13 4.5" fill="none" stroke="var(--color-good)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function Microphone() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true" className="shrink-0">
      <rect x="8.5" y="2.5" width="7" height="12" rx="3.5" fill="none" stroke="var(--color-overlay-text)" strokeWidth="2" strokeLinecap="round" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3.5" fill="none" stroke="var(--color-overlay-text)" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

export function Unlinked() {
  return (
    <svg width="24" height="24" viewBox="0 0 28 28" aria-hidden="true" className="shrink-0">
      <path d="M9 13l-3 3a4 4 0 0 0 6 6l3-3" fill="none" stroke="var(--color-primary)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M19 15l3-3a4 4 0 0 0-6-6l-3 3" fill="none" stroke="var(--color-primary)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 4l20 20" fill="none" stroke="var(--color-primary)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function MatIllustration() {
  const lines = Array.from({ length: 21 }, (_, index) => `M0 ${20 + index * 6}H320`).join('')
  return (
    <svg width="320" height="160" viewBox="0 0 320 160" aria-hidden="true" className="shrink-0">
      <rect x="0" y="0" width="320" height="160" rx="4" fill="var(--color-surface)" />
      <path d={lines} fill="none" stroke="#1D1B1614" />
      <rect x="0" y="0" width="320" height="12" fill="var(--color-primary)" />
      <rect x="0" y="148" width="320" height="12" fill="var(--color-primary)" />
    </svg>
  )
}

export function Waveform() {
  const bars = [
    [0, 7, 6],
    [6, 3, 14],
    [12, 0, 20],
    [18, 5, 10],
    [24, 2, 16],
    [30, 6, 8],
    [36, 8, 4]
  ]
  return (
    <svg width="40" height="20" viewBox="0 0 40 20" aria-hidden="true" className="shrink-0">
      {bars.map(([x, y, height]) => (
        <rect key={x} x={x} y={y} width="4" height={height} rx="2" fill="var(--color-primary)" />
      ))}
    </svg>
  )
}
