import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { queryKeys, useRoundBreak, useSessions, useSummaryListener, type SessionMeta } from '../services'

const CATCH_UP_POLL_MS = 2_000
const CATCH_UP_LIMIT_MS = 20_000

export type ScreenName = 'sessions' | 'replay' | 'learning' | 'stats' | 'coach' | 'controls'

export interface Focus {
  round: number
  frame: number
}

interface OpenOptions {
  sessionId?: string
  focus?: Focus
}

export interface AwaitedRound {
  sessionId: string
  round: number
}

interface Awaiting extends AwaitedRound {
  since: number
}

type RoundList = { round: number }[] | undefined

interface Frame {
  screen: ScreenName
  focus: Focus | null
  open: (screen: ScreenName, options?: OpenOptions) => void
  sessions: SessionMeta[] | undefined
  sessionsFailed: boolean
  selectedId: string | null
  selected: SessionMeta | undefined
  select: (sessionId: string) => void
  awaited: AwaitedRound | null
}

const FrameContext = createContext<Frame | null>(null)

export function useFrame(): Frame {
  const frame = useContext(FrameContext)
  if (!frame) throw new Error('useFrame needs FrameProvider')
  return frame
}

export function FrameProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient()
  const sessionsQuery = useSessions()
  const [screen, setScreen] = useState<ScreenName>('sessions')
  const [focus, setFocus] = useState<Focus | null>(null)
  const [picked, setPicked] = useState<string | null>(null)

  const sessions = sessionsQuery.data
  const selectedId = picked ?? sessions?.[0]?.session_id ?? null
  const selected = sessions?.find((session) => session.session_id === selectedId)

  const select = useCallback((sessionId: string) => setPicked(sessionId), [])

  const open = useCallback((next: ScreenName, options: OpenOptions = {}) => {
    if (options.sessionId) setPicked(options.sessionId)
    setFocus(options.focus ?? null)
    setScreen(next)
  }, [])

  const [awaited, setAwaited] = useState<Awaiting | null>(null)
  const { liveSet, isLive } = useRoundBreak()
  const seen = useRef<{ liveSet: string | undefined; isLive: boolean }>({ liveSet: undefined, isLive: false })

  const refreshSet = useCallback((id: string) => {
    void client.invalidateQueries({ queryKey: queryKeys.sessions() })
    void client.invalidateQueries({ queryKey: queryKeys.session(id) })
    void client.invalidateQueries({ queryKey: ['brain', 'recording', id] })
    void client.invalidateQueries({ queryKey: queryKeys.stats(id) })
    void client.invalidateQueries({ queryKey: queryKeys.learning(id) })
    void client.invalidateQueries({ queryKey: queryKeys.insights(id) })
  }, [client])

  useSummaryListener((summary) => {
    const id = summary.session_id
    refreshSet(id)
    void client.invalidateQueries({ queryKey: queryKeys.report(id) })
    void client.invalidateQueries({ queryKey: ['analytics', 'trends'] })
    setAwaited({ sessionId: id, round: summary.round, since: Date.now() })
  })

  useEffect(() => {
    const previous = seen.current
    if (liveSet && liveSet !== previous.liveSet) void client.invalidateQueries({ queryKey: queryKeys.sessions() })
    if (previous.isLive && !isLive && previous.liveSet) refreshSet(previous.liveSet)
    seen.current = { liveSet, isLive }
  }, [liveSet, isLive, client, refreshSet])

  useEffect(() => {
    if (!awaited) return
    const has = (rounds: RoundList) => Boolean(rounds?.some((entry) => entry.round >= awaited.round))
    const timer = window.setInterval(() => {
      const stats = client.getQueryData<{ rounds: { round: number }[] }>(queryKeys.stats(awaited.sessionId))
      const learning = client.getQueryData<{ rounds: { round: number }[] }>(queryKeys.learning(awaited.sessionId))
      const statsReady = has(stats?.rounds)
      const learningReady = has(learning?.rounds)
      if ((statsReady && learningReady) || Date.now() - awaited.since >= CATCH_UP_LIMIT_MS) {
        setAwaited(null)
        return
      }
      if (!statsReady) void client.invalidateQueries({ queryKey: queryKeys.stats(awaited.sessionId) })
      if (!learningReady) void client.invalidateQueries({ queryKey: queryKeys.learning(awaited.sessionId) })
      void client.invalidateQueries({ queryKey: queryKeys.insights(awaited.sessionId) })
    }, CATCH_UP_POLL_MS)
    return () => window.clearInterval(timer)
  }, [awaited, client])

  const awaitedRound = useMemo<AwaitedRound | null>(
    () => (awaited ? { sessionId: awaited.sessionId, round: awaited.round } : null),
    [awaited]
  )

  const value = useMemo<Frame>(
    () => ({
      screen,
      focus,
      open,
      sessions,
      sessionsFailed: sessionsQuery.isError,
      selectedId,
      selected,
      select,
      awaited: awaitedRound
    }),
    [screen, focus, open, sessions, sessionsQuery.isError, selectedId, selected, select, awaitedRound]
  )

  return <FrameContext.Provider value={value}>{children}</FrameContext.Provider>
}

export function useSavingRound(sessionId: string, rounds: RoundList): number | null {
  const { awaited } = useFrame()
  if (!awaited || awaited.sessionId !== sessionId) return null
  return rounds?.some((entry) => entry.round >= awaited.round) ? null : awaited.round
}

export function SavingNote({ sessionId, rounds }: { sessionId: string; rounds: RoundList }) {
  const round = useSavingRound(sessionId, rounds)
  if (round === null) return null
  return <p role="status" className="text-base/sm text-text-muted">Round {round} is still being saved.</p>
}
