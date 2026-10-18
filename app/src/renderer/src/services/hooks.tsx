import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore, type ReactNode } from 'react'
import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ServiceName } from '../../../shared/bridge'
import { analytics, brain, replay } from './calls'
import type { CoachMessage, Config, GameEvent, Report, RoundSummary } from './contracts'
import type { ServiceError } from './http'
import type { RecordingOptions } from './recording'
import { serviceStatus, servicesBackOnline, startHealthPolling } from './status'
import {
  coachMessages,
  gameEvents,
  latestCoach,
  latestPlan,
  latestState,
  latestSummary,
  roundSummaries,
  streams,
  type StreamName
} from './streams'

declare module '@tanstack/react-query' {
  interface Register {
    defaultError: ServiceError
  }
}

const CONFIG_REFRESH_MS = 5_000

export const queryKeys = {
  sessions: () => ['brain', 'sessions'] as const,
  session: (sessionId: string) => ['brain', 'session', sessionId] as const,
  recording: (sessionId: string, states: boolean) => ['brain', 'recording', sessionId, states] as const,
  profiles: (player: string) => ['brain', 'profiles', player] as const,
  config: () => ['brain', 'config'] as const,
  report: (sessionId: string) => ['replay', 'report', sessionId] as const,
  stats: (sessionId: string) => ['analytics', 'stats', sessionId] as const,
  trends: (player: string, character: string, stat?: string) =>
    ['analytics', 'trends', player, character, stat ?? null] as const,
  learning: (sessionId: string) => ['analytics', 'learning', sessionId] as const
}

function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, networkMode: 'always' },
      mutations: { retry: false, networkMode: 'always' }
    }
  })
}

export function ServicesProvider({ children }: { children: ReactNode }) {
  const [client] = useState(createQueryClient)
  useEffect(() => startHealthPolling(), [])
  useEffect(
    () => servicesBackOnline.listen((service: ServiceName) => void client.invalidateQueries({ queryKey: [service] })),
    [client]
  )
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

export function useSessions() {
  return useQuery({ queryKey: queryKeys.sessions(), queryFn: brain.listSessions })
}

export function useSession(sessionId: string) {
  return useQuery({ queryKey: queryKeys.session(sessionId), queryFn: () => brain.getSession(sessionId) })
}

export function useRecording(sessionId: string, options: RecordingOptions = {}) {
  const states = options.states === true
  return useQuery({
    queryKey: queryKeys.recording(sessionId, states),
    queryFn: () => brain.getRecording(sessionId, { states })
  })
}

export function useProfiles(player: string) {
  return useQuery({ queryKey: queryKeys.profiles(player), queryFn: () => brain.getProfiles(player) })
}

export function useConfig() {
  return useQuery({ queryKey: queryKeys.config(), queryFn: brain.getConfig, refetchInterval: CONFIG_REFRESH_MS })
}

export function useReport(sessionId: string) {
  return useQuery({
    queryKey: queryKeys.report(sessionId),
    queryFn: () => replay.getReport(sessionId),
    refetchInterval: (query) => query.state.data === null ? 3_000 : false
  })
}

export function useStats(sessionId: string) {
  return useQuery({ queryKey: queryKeys.stats(sessionId), queryFn: () => analytics.getStats(sessionId) })
}

export function useTrends(player: string, character: string, stat?: string) {
  return useQuery({
    queryKey: queryKeys.trends(player, character, stat),
    queryFn: () => analytics.getTrends(player, character, stat)
  })
}

export function useLearning(sessionId: string) {
  return useQuery({
    queryKey: queryKeys.learning(sessionId),
    queryFn: () => analytics.getLearning(sessionId),
    enabled: sessionId.length > 0
  })
}

export function usePostConfig() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: brain.postConfig,
    onSuccess: (config: Config) => client.setQueryData(queryKeys.config(), config)
  })
}

export function useAnalyze(sessionId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => replay.analyze(sessionId),
    onSuccess: (report: Report) => client.setQueryData(queryKeys.report(sessionId), report)
  })
}

export function useChat() {
  return useMutation({ mutationFn: replay.chat })
}

export function useLiveState() {
  return useSyncExternalStore(latestState.subscribe, latestState.get)
}

export function useLatestPlan() {
  return useSyncExternalStore(latestPlan.subscribe, latestPlan.get)
}

export function useLatestCoach() {
  return useSyncExternalStore(latestCoach.subscribe, latestCoach.get)
}

export function useLatestSummary() {
  return useSyncExternalStore(latestSummary.subscribe, latestSummary.get)
}

function useListener<T>(listen: (listener: (value: T) => void) => () => void, listener: (value: T) => void): void {
  const current = useRef(listener)
  useLayoutEffect(() => {
    current.current = listener
  })
  useEffect(() => listen((value) => current.current(value)), [listen])
}

export function useEventListener(listener: (event: GameEvent) => void): void {
  useListener(gameEvents.listen, listener)
}

export function useCoachListener(listener: (message: CoachMessage) => void): void {
  useListener(coachMessages.listen, listener)
}

export function useSummaryListener(listener: (summary: RoundSummary) => void): void {
  useListener(roundSummaries.listen, listener)
}

export function useStreamStatus(stream: StreamName) {
  const status = streams[stream].status
  return useSyncExternalStore(status.subscribe, status.get)
}

export function useServiceStatus(service: ServiceName) {
  const status = serviceStatus[service]
  return useSyncExternalStore(status.subscribe, status.get)
}
