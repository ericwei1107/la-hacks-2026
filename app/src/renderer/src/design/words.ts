import type { Character } from '../services'

const CHARACTERS: Record<Character, string> = {
  devil_jin: 'Devil Jin',
  kazuya: 'Kazuya',
  king: 'King',
  shaheen: 'Shaheen',
  unknown: 'Opponent'
}

const HABITS: Record<string, { name: string; short: string }> = {
  low_defense: { name: 'Low blocks', short: 'low-block' },
  sidestep_dir: { name: 'Sidestep direction', short: 'sidestep' },
  throw_break: { name: 'Throw breaks', short: 'throw-break' },
  after_block: { name: 'After you block', short: 'after-block' }
}

const SITUATIONS: Record<string, string> = {
  neutral: 'Neutral',
  wakeup: 'Wake-up',
  whiff_punished: 'Whiff punished',
  throw: 'Throws',
  sidestep_dir: 'Sidesteps'
}

const DIRECTIONS = ['df', 'db', 'uf', 'ub', 'd', 'f', 'b', 'u', 'n']

export function humanize(key: string): string {
  const words = key.replace(/_/g, ' ').trim()
  return words ? `${words[0].toUpperCase()}${words.slice(1)}` : words
}

export function characterName(key: string | undefined): string {
  if (!key) return CHARACTERS.unknown
  return CHARACTERS[key as Character] ?? humanize(key)
}

function habitKey(key: string): string {
  return key.startsWith('after_block') ? 'after_block' : key
}

export function habitName(key: string): string {
  return HABITS[habitKey(key)]?.name ?? humanize(key)
}

export function habitShort(key: string): string {
  return HABITS[habitKey(key)]?.short ?? humanize(key).toLowerCase()
}

export function notation(move: string): string {
  if (/[+/]/.test(move)) return move
  const direction = DIRECTIONS.find((candidate) => move.startsWith(candidate) && /^\d+$/.test(move.slice(candidate.length)))
  const buttons = direction ? move.slice(direction.length) : move
  if (!/^\d+$/.test(buttons)) return move
  const joined = buttons.split('').join('+')
  return direction ? `${direction}+${joined}` : joined
}

export function situationName(key: string): string {
  if (key.startsWith('after_block:')) return `After blocking ${notation(key.slice('after_block:'.length))}`
  if (SITUATIONS[key]) return SITUATIONS[key]
  if (HABITS[habitKey(key)]) return habitName(key)
  return humanize(key)
}

export function optionName(key: string): string {
  return humanize(key)
}

export function withCommand(name: string, command: string | undefined): string {
  return command ? `${name} (${command})` : name
}

export const NOTATION_TOKEN = /\b((?:d|f|b|u|n|df|db|uf|ub)\+[1-4](?:\+[1-4])*|[1-4]\+[1-4](?:\+[1-4])*|(?:d|f|b|u)\/(?:d|f|b|u))\b/g
