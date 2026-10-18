import * as analyticsCalls from './analytics'
import * as brainCalls from './brain'
import { getRecording } from './recording'
import * as replayCalls from './replay'
import { health } from './status'

export const brain = { ...brainCalls, getRecording }
export const replay = replayCalls
export const analytics = analyticsCalls
export { health }
