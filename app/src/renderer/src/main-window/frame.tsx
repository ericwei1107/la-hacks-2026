import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { queryKeys, useSessions, useSummaryListener, type SessionMeta } from '../services'

export type ScreenName = 'sessions' | 'replay' | 'learning' | 'stats' | 'coach' | 'controls'

export interface Focus {
  round: number
  frame: number
}

interface OpenOptions {
  sessionId?: string
  focus?: Focus
}

interface Frame {
  screen: ScreenName
  focus: Focus | null
  open: (screen: ScreenName, options?: OpenOptions) => void
  sessions: SessionMeta[] | undefined
  sessionsFailed: boolean
  selectedId: string | null
  selected: SessionMeta | undefined
  select: (sessionId: string) => void
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

  useSummaryListener((summary) => {
    if (summary.session_id !== selectedId) return
    const id = summary.session_id
    void client.invalidateQueries({ queryKey: queryKeys.sessions() })
    void client.invalidateQueries({ queryKey: queryKeys.session(id) })
    void client.invalidateQueries({ queryKey: ['brain', 'recording', id] })
    void client.invalidateQueries({ queryKey: queryKeys.stats(id) })
    void client.invalidateQueries({ queryKey: queryKeys.learning(id) })
    void client.invalidateQueries({ queryKey: queryKeys.report(id) })
    void client.invalidateQueries({ queryKey: ['analytics', 'trends'] })
  })

  const value = useMemo<Frame>(
    () => ({
      screen,
      focus,
      open,
      sessions,
      sessionsFailed: sessionsQuery.isError,
      selectedId,
      selected,
      select
    }),
    [screen, focus, open, sessions, sessionsQuery.isError, selectedId, selected, select]
  )

  return <FrameContext.Provider value={value}>{children}</FrameContext.Provider>
}
