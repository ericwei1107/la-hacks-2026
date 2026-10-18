const time = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' })
const day = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' })

function isToday(date: Date): boolean {
  const now = new Date()
  return date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth() && date.getDate() === now.getDate()
}

export function dayLabel(iso: string): string {
  const date = new Date(iso)
  return isToday(date) ? 'Today' : day.format(date)
}

export function setTime(iso: string): string {
  return `${dayLabel(iso)}, ${time.format(new Date(iso))}`
}

export function setTimeInSentence(iso: string): string {
  return `${dayLabel(iso)} at ${time.format(new Date(iso))}`
}

export function shortClock(iso: string): string {
  return time.format(new Date(iso)).replace(/\s?[AP]M$/, '')
}

export function duration(fromIso: string, toIso: string): string {
  const seconds = Math.max(0, Math.round((new Date(toIso).getTime() - new Date(fromIso).getTime()) / 1000))
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

export function percent(rate: number | null | undefined): string {
  if (rate === null || rate === undefined) return '—'
  return `${Math.round(rate * 100)}%`
}

export function signed(value: number): string {
  if (value > 0) return `+${value}`
  if (value < 0) return `−${Math.abs(value)}`
  return '0'
}

export function score(first: number, second: number): string {
  return `${first}–${second}`
}

const SHARES: [number, string][] = [
  [1 / 2, 'half'],
  [1 / 3, 'a third'],
  [1 / 4, 'a quarter'],
  [1 / 5, 'a fifth']
]

export function share(part: number, whole: number): string {
  if (whole <= 0) return '0%'
  const ratio = part / whole
  const named = SHARES.find(([value]) => Math.abs(ratio - value) <= 0.03)
  return named ? named[1] : `${Math.round(ratio * 100)}%`
}

export function oneDecimal(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}
