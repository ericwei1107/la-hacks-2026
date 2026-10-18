import { useEffect, useLayoutEffect, useRef } from 'react'
import { useRoundBreak } from '../services'
import { useFrame } from './frame'
import { requestTalk } from './talkRequests'

export function GlobalTalk() {
  const { open } = useFrame()
  const { isLive, roundBreak } = useRoundBreak()
  const inMatch = isLive && roundBreak?.matchOver !== true
  const latest = useRef({ inMatch, open })

  useLayoutEffect(() => {
    latest.current = { inMatch, open }
  })

  useEffect(() => {
    const bridge = window.kumite
    if (!bridge?.onTalk) return
    return bridge.onTalk(() => {
      if (latest.current.inMatch) return
      latest.current.open('coach')
      requestTalk()
    })
  }, [])

  return null
}
