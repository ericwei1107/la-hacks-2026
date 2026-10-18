import { Sidebar } from './Sidebar'
import { FrameProvider, useFrame } from './frame'
import { GlobalTalk } from './GlobalTalk'
import { Coach } from './screens/Coach'
import { Controls } from './screens/Controls'
import { Learning } from './screens/Learning'
import { ReplayAnalysis } from './screens/ReplayAnalysis'
import { Sessions } from './screens/Sessions'
import { Stats } from './screens/Stats'
import { useCoachRecordVoice } from '../voice'

function CurrentScreen() {
  const { screen } = useFrame()
  if (screen === 'replay') return <ReplayAnalysis />
  if (screen === 'learning') return <Learning />
  if (screen === 'stats') return <Stats />
  if (screen === 'coach') return <Coach />
  if (screen === 'controls') return <Controls />
  return <Sessions />
}

function CoachRecordVoice() {
  useCoachRecordVoice()
  return null
}

export function MainWindow() {
  return (
    <FrameProvider>
      <CoachRecordVoice />
      <GlobalTalk />
      <div className="mat-ground flex h-full overflow-hidden">
        <Sidebar />
        <div className="flex grow basis-0 flex-col overflow-auto">
          <CurrentScreen />
        </div>
      </div>
    </FrameProvider>
  )
}
