import {
  useConfig,
  useLatestCoach,
  useLatestSummary,
  useLiveState,
  useServiceStatus,
  useSessions,
  useStreamStatus,
  type ServiceName,
  type StreamName
} from './services'

function ServiceLine({ service }: { service: ServiceName }) {
  const status = useServiceStatus(service)
  return (
    <li>
      {service}: {status.state} at {status.address.url} ({status.address.source})
      {status.version ? `, version ${status.version}` : ''}
      {status.address.warning ? `, warning: ${status.address.warning}` : ''}
    </li>
  )
}

function StreamLine({ stream }: { stream: StreamName }) {
  return (
    <li>
      {stream} stream: {useStreamStatus(stream)}
    </li>
  )
}

export function IntegrationCheck() {
  const live = useLiveState()
  const coach = useLatestCoach()
  const summary = useLatestSummary()
  const sessions = useSessions()
  const config = useConfig()

  return (
    <main>
      <h1>Kumite</h1>
      <p>Integration check on {window.kumite?.platform ?? 'a plain browser'}</p>
      <ul>
        <ServiceLine service="brain" />
        <ServiceLine service="replay" />
        <ServiceLine service="analytics" />
        <StreamLine stream="state" />
        <StreamLine stream="coach" />
      </ul>
      <ul>
        <li>
          sessions:{' '}
          {sessions.isPending
            ? 'loading'
            : sessions.isError
              ? `${sessions.error.kind}: ${sessions.error.message}`
              : `${sessions.data.length} (${sessions.data[0]?.session_id ?? 'none'})`}
        </li>
        <li>
          config:{' '}
          {config.isPending
            ? 'loading'
            : config.isError
              ? `${config.error.kind}: ${config.error.message}`
              : `difficulty ${config.data.difficulty}, bot ${config.data.bot_character}, player ${config.data.player}`}
        </li>
        <li>
          live state:{' '}
          {live ? `round ${live.record.round}, frame ${live.record.frame}, ${live.record.derived.situation}` : 'none yet'}
        </li>
        <li>coach: {coach ? `round ${coach.record.round}: ${coach.record.text}` : 'none yet'}</li>
        <li>
          round summary:{' '}
          {summary ? `round ${summary.record.round}, ${summary.record.top_habits.length} top habits` : 'none yet'}
        </li>
      </ul>
    </main>
  )
}
