export type AnswerBlock =
  | { kind: 'priority'; order: 'First' | 'Next'; title: string; observation: string; drill: string | null }
  | { kind: 'moment'; label: string; text: string }
  | { kind: 'text'; text: string }

const BOUNDARY = /(?=\b(?:Start with |Next, work on |Round \d+, frame \d+: ))/
const PRIORITY = /^(Start with|Next, work on) ([^.]+)\.\s*([\s\S]*)$/
const MOMENT = /^(Round \d+, frame \d+): ([\s\S]*)$/
const DRILL = 'In Practice,'

function capitalized(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

function block(segment: string): AnswerBlock {
  const priority = PRIORITY.exec(segment)
  if (priority) {
    const [, lead, title, rest] = priority
    const at = rest.indexOf(DRILL)
    return {
      kind: 'priority',
      order: lead === 'Start with' ? 'First' : 'Next',
      title: capitalized(title.trim()),
      observation: (at < 0 ? rest : rest.slice(0, at)).trim(),
      drill: at < 0 ? null : rest.slice(at).trim()
    }
  }
  const moment = MOMENT.exec(segment)
  if (moment) return { kind: 'moment', label: moment[1], text: moment[2].trim() }
  return { kind: 'text', text: segment }
}

export function answerBlocks(text: string): AnswerBlock[] {
  return text
    .split(BOUNDARY)
    .map((segment) => segment.trim())
    .filter((segment) => segment.length > 0)
    .map(block)
}
