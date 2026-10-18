import { useEffect, useRef, useState } from 'react'
import { EmptyState, KeyCap, Microphone, PlayMark, SendArrow, Toggle } from '../../design'
import { useChat, useConfig, usePostConfig, type ChatCitation, type SessionMeta } from '../../services'
import { useFrame } from '../frame'
import { keyLabel, usePushToTalkKey } from '../pushToTalk'
import { Screen, ScreenBanner, useOfflineService } from '../Screen'
import { useHoldToTalk } from '../../voice'

interface Turn {
  role: 'user' | 'coach'
  text: string
  citations?: ChatCitation[]
  failed?: boolean
}

const threads = new Map<string, Turn[]>()

function CoachAnswer({ turn, onCitation }: { turn: Turn; onCitation: (citation: ChatCitation) => void }) {
  return (
    <div className="flex max-w-[680px] flex-col gap-3">
      <span className="text-sm leading-[18px] font-bold text-primary-text">Coach</span>
      <p className={`text-lg leading-[30px] ${turn.failed ? 'text-text-muted' : 'text-text'}`}>{turn.text}</p>
      {turn.citations && turn.citations.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {turn.citations.map((citation) => (
            <button
              key={`${citation.round}:${citation.frame}`}
              type="button"
              onClick={() => onCitation(citation)}
              className="focus-ring flex h-8 items-center gap-2 rounded-[16px] border-[1.5px] border-solid border-primary bg-surface px-3 text-sm leading-[18px] font-bold text-primary-text"
            >
              <PlayMark />
              Round {citation.round}, frame {citation.frame}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function Conversation({ session, disabled }: { session: SessionMeta; disabled: boolean }) {
  const { open } = useFrame()
  const config = useConfig()
  const postConfig = usePostConfig()
  const chat = useChat()
  const pushToTalk = usePushToTalkKey()
  const [turns, setTurns] = useState<Turn[]>(() => threads.get(session.session_id) ?? [])
  const [draft, setDraft] = useState('')
  const end = useRef<HTMLDivElement>(null)

  useEffect(() => {
    threads.set(session.session_id, turns)
    end.current?.scrollIntoView({ block: 'end' })
  }, [session.session_id, turns])

  const ask = async (message: string) => {
    if (!message || chat.isPending) return
    const history = turns.filter((turn) => !turn.failed).map(({ role, text }) => ({ role, text }))
    setTurns((current) => [...current, { role: 'user', text: message }])
    try {
      const reply = await chat.mutateAsync({
        session_id: session.session_id,
        player: config.data?.player ?? session.player,
        message,
        history
      })
      setTurns((current) => [...current, { role: 'coach', text: reply.text, citations: reply.citations }])
    } catch (error) {
      setTurns((current) => [...current, { role: 'coach', text: `Couldn't reach the coach. ${(error as Error).message}`, failed: true }])
    }
  }

  const available = !disabled && !chat.isPending && Boolean(window.kumite?.transcribe)
  const talk = useHoldToTalk((text) => void ask(text), available)
  const { start, stop } = talk

  const send = () => {
    const message = draft.trim()
    if (!message || chat.isPending) return
    setDraft('')
    talk.clearNote()
    void ask(message)
  }

  useEffect(() => {
    if (!available) stop()
  }, [available, stop])

  useEffect(() => {
    const typing = () => {
      const element = document.activeElement
      return element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || (element instanceof HTMLElement && element.isContentEditable)
    }
    const down = (event: KeyboardEvent) => {
      if (event.repeat || typing() || keyLabel(event) !== pushToTalk) return
      event.preventDefault()
      void start()
    }
    const up = (event: KeyboardEvent) => {
      if (keyLabel(event) === pushToTalk) stop()
    }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    window.addEventListener('blur', stop)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
      window.removeEventListener('blur', stop)
    }
  }, [pushToTalk, start, stop])

  const talkLabel = talk.phase === 'listening' ? 'Listening…' : talk.phase === 'transcribing' ? 'Transcribing…' : 'Hold to talk'

  const voice = postConfig.isPending ? (postConfig.variables?.voice ?? config.data?.voice) : config.data?.voice

  return (
    <>
      <div className="flex grow basis-0 flex-col gap-[28px]">
        {turns.length === 0 && !chat.isPending && <p className="text-lg/lg text-text-muted">Ask about this set. Try: Why did I lose round 2?</p>}
        {turns.map((turn, index) =>
          turn.role === 'user' ? (
            <div key={index} className="flex justify-end">
              <p className="max-w-[520px] rounded-[12px] rounded-br-[4px] bg-primary px-[18px] py-[14px] text-lg/lg text-overlay-text">{turn.text}</p>
            </div>
          ) : (
            <CoachAnswer
              key={index}
              turn={turn}
              onCitation={(citation) => open('replay', { sessionId: session.session_id, focus: citation })}
            />
          )
        )}
        {chat.isPending && (
          <div className="flex flex-col gap-3">
            <span className="text-sm leading-[18px] font-bold text-primary-text">Coach</span>
            <p className="text-lg leading-[30px] text-text-muted">Thinking…</p>
          </div>
        )}
        <div ref={end} />
      </div>
      <div className="sticky bottom-0 flex flex-col gap-2 border-t-2 border-solid border-t-primary bg-bg pt-6">
        <div className="flex items-center gap-4">
          <button
            type="button"
            disabled={!available}
            aria-pressed={talk.phase === 'listening'}
            onPointerDown={(event) => {
              if (event.button === 0) void start()
            }}
            onPointerUp={stop}
            onPointerLeave={stop}
            onPointerCancel={stop}
            onContextMenu={(event) => event.preventDefault()}
            className={`focus-ring flex h-[72px] shrink-0 items-center gap-[14px] rounded-md bg-primary pr-6 pl-[22px] select-none disabled:opacity-60 ${talk.phase === 'listening' ? 'ring-4 ring-primary/30' : ''}`}
          >
            <Microphone />
            <span className="text-[22px] leading-lg font-bold text-overlay-text">{talkLabel}</span>
            <KeyCap raised>{pushToTalk}</KeyCap>
          </button>
          <form
            className="flex h-[72px] grow basis-0 items-center justify-between gap-3 rounded-md border-[1.5px] border-solid border-[#1D1B1640] bg-surface px-[20px] focus-within:border-primary"
            onSubmit={(event) => {
              event.preventDefault()
              send()
            }}
          >
            <input
              value={draft}
              onChange={(event) => setDraft(event.currentTarget.value)}
              disabled={disabled || chat.isPending}
              placeholder="Or type a question about this set"
              aria-label="Question for the coach"
              className="grow basis-0 bg-transparent text-lg/base text-text outline-none placeholder:text-text-muted"
            />
            <button type="submit" aria-label="Send" disabled={disabled || chat.isPending || !draft.trim()} className="focus-ring rounded-sm text-text-muted enabled:hover:text-primary">
              <SendArrow />
            </button>
          </form>
          <label className="flex h-[40px] items-center gap-3 pl-2">
            <span className="text-base/sm font-medium text-text">Coach voice</span>
            <Toggle
              label="Coach voice"
              checked={Boolean(voice)}
              disabled={!config.data}
              onChange={(checked) => postConfig.mutate({ voice: checked })}
            />
          </label>
        </div>
        {talk.note && <p role="status" className="text-sm leading-5 text-text-muted">{talk.note}</p>}
      </div>
    </>
  )
}

export function Coach() {
  const { selected, sessions } = useFrame()
  const offline = useOfflineService(['replay', 'brain'])
  return (
    <Screen title="Coach" picker gap="gap-[28px]">
      <ScreenBanner service={offline} line="The conversation is saved here; you can ask again when it reconnects." />
      {sessions && sessions.length === 0 && <EmptyState headline="No set to talk about yet." line="Play a set against Kumite, then ask the coach about it." />}
      {selected && <Conversation key={selected.session_id} session={selected} disabled={offline === 'replay'} />}
    </Screen>
  )
}
