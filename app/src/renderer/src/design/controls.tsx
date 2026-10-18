import type { ButtonHTMLAttributes, CSSProperties, ReactNode, SelectHTMLAttributes } from 'react'
import { Chevron } from './icons'

export function Button({ className = '', children, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={`focus-ring flex h-10 shrink-0 items-center gap-2 rounded-sm bg-primary px-4 text-base/sm font-bold text-overlay-text disabled:opacity-60 ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}

export function TextButton({ className = '', children, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={`focus-ring rounded-sm text-base/sm font-bold text-primary-text underline decoration-1 underline-offset-2 disabled:opacity-60 ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}

interface ToggleProps {
  checked: boolean
  label: string
  disabled?: boolean
  onChange: (checked: boolean) => void
}

export function Toggle({ checked, label, disabled, onChange }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`focus-ring flex h-[28px] w-12 shrink-0 items-center rounded-[14px] p-[3px] transition-colors duration-150 disabled:opacity-60 ${
        checked ? 'justify-end bg-primary' : 'justify-start bg-track'
      }`}
    >
      <span className="size-[22px] shrink-0 rounded-[11px] bg-surface" />
    </button>
  )
}

interface SliderProps {
  label: string
  min: number
  max: number
  step: number
  value: number
  disabled?: boolean
  onInput: (value: number) => void
  onCommit: (value: number) => void
}

export function Slider({ label, min, max, step, value, disabled, onInput, onCommit }: SliderProps) {
  const fill = ((value - min) / (max - min)) * 100
  return (
    <input
      type="range"
      aria-label={label}
      className="slider"
      min={min}
      max={max}
      step={step}
      value={value}
      disabled={disabled}
      style={{ '--fill': `${fill}%` } as CSSProperties}
      onChange={(event) => onInput(Number(event.currentTarget.value))}
      onPointerUp={(event) => onCommit(Number(event.currentTarget.value))}
      onKeyUp={(event) => {
        if (event.key.startsWith('Arrow') || ['Home', 'End', 'PageUp', 'PageDown'].includes(event.key)) {
          onCommit(Number(event.currentTarget.value))
        }
      }}
    />
  )
}

interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'size'> {
  size?: 'field' | 'picker' | 'compact'
}

export function Select({ size = 'picker', className = '', children, ...props }: SelectProps) {
  const shape = {
    field: 'h-12 bg-surface border-[#1D1B1640] font-bold px-[14px]',
    picker: 'h-10 border-primary font-medium px-[14px]',
    compact: 'h-9 bg-surface border-primary font-medium px-3'
  }[size]
  return (
    <div className={`relative flex ${className}`}>
      <select
        className={`focus-ring w-full appearance-none rounded-sm border-[1.5px] border-solid pr-9 text-base/sm text-text disabled:opacity-60 ${shape}`}
        {...props}
      >
        {children}
      </select>
      <span className="pointer-events-none absolute top-1/2 right-[14px] -translate-y-1/2">
        <Chevron />
      </span>
    </div>
  )
}

export function KeyCap({ children, raised = false }: { children: ReactNode; raised?: boolean }) {
  return (
    <span
      className={`flex h-[36px] min-w-[36px] items-center justify-center rounded-sm bg-surface px-[10px] font-mono text-lg/base font-bold text-primary-text ${
        raised ? 'border-b-[3px] border-solid border-b-track' : 'border-[1.5px] border-b-[3px] border-solid border-[#1D1B1633]'
      }`}
    >
      {children}
    </span>
  )
}

interface ChipProps {
  label: string
  count: number
  selected: boolean
  onSelect: () => void
}

export function Chip({ label, count, selected, onSelect }: ChipProps) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
      className={`focus-ring flex h-[36px] shrink-0 items-center gap-2 rounded-[18px] px-[14px] ${
        selected ? 'bg-primary' : 'border-[1.5px] border-solid border-[#1D1B1640]'
      }`}
    >
      <span className={`text-base/sm ${selected ? 'font-bold text-overlay-text' : 'font-medium text-text'}`}>{label}</span>
      <span className={`font-mono text-base/sm font-medium ${selected ? 'text-overlay-muted' : 'text-text-muted'}`}>{count}</span>
    </button>
  )
}

interface MeterProps {
  value: number
  strong?: boolean
}

export function Meter({ value, strong = true }: MeterProps) {
  return (
    <div className="flex h-3 grow basis-0 overflow-clip rounded-[3px] bg-track">
      <div
        className={`h-full ${strong ? 'bg-primary' : 'bg-text-muted'}`}
        style={{ width: `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%` }}
      />
    </div>
  )
}
