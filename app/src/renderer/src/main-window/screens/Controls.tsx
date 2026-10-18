import { useEffect, useState } from 'react'
import { KeyCap, Select, Skeleton, Slider, TextButton, Toggle } from '../../design'
import { useConfig, usePostConfig, type Character, type ConfigUpdate, type Knobs } from '../../services'
import { keyLabel, setPushToTalkKey, usePushToTalkKey } from '../pushToTalk'
import { Screen, ScreenBanner, useOfflineService } from '../Screen'

const PRESETS = [
  { level: 1, name: 'Rookie', reaction_delay_frames: 30, punish_accuracy: 0.4, exploit_weight: 0.2 },
  { level: 2, name: 'Novice', reaction_delay_frames: 24, punish_accuracy: 0.6, exploit_weight: 0.4 },
  { level: 3, name: 'Intermediate', reaction_delay_frames: 18, punish_accuracy: 0.8, exploit_weight: 0.6 },
  { level: 4, name: 'Advanced', reaction_delay_frames: 12, punish_accuracy: 0.92, exploit_weight: 0.8 },
  { level: 5, name: 'Tekken God', reaction_delay_frames: 6, punish_accuracy: 1, exploit_weight: 1 }
]

const GROW = ['grow', 'grow', 'grow-[1.3]', 'grow-[1.1]', 'grow-[1.2]']

const CHARACTERS: [Character, string][] = [
  ['kazuya', 'Kazuya'],
  ['devil_jin', 'Devil Jin'],
  ['king', 'King'],
  ['shaheen', 'Shaheen']
]

type KnobKey = 'reaction_delay_frames' | 'punish_accuracy' | 'exploit_weight'

function KnobSlider({ label, knob, value, low, high, format, disabled, onSave }: {
  label: string
  knob: KnobKey
  value: number
  low: string
  high: string
  format: (value: number) => string
  disabled: boolean
  onSave: (knob: KnobKey, value: number) => void
}) {
  const delay = knob === 'reaction_delay_frames'
  const [draft, setDraft] = useState(value)
  useEffect(() => setDraft(value), [value])
  const position = delay ? 36 - draft : Math.round(draft * 100)
  const toValue = (raw: number) => (delay ? 36 - raw : raw / 100)
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <span className="text-base/sm font-bold text-text">{label}</span>
        <span className={`text-lg/base text-text ${delay ? 'font-mono font-[600]' : 'font-[900]'}`}>{format(draft)}</span>
      </div>
      <Slider
        label={label}
        min={delay ? 6 : 0}
        max={delay ? 30 : 100}
        step={1}
        value={position}
        disabled={disabled}
        onInput={(raw) => setDraft(toValue(raw))}
        onCommit={(raw) => onSave(knob, toValue(raw))}
      />
      <div className="flex justify-between text-sm leading-[18px] text-text-muted">
        <span>{low}</span>
        <span>{high}</span>
      </div>
    </div>
  )
}

export function Controls() {
  const config = useConfig()
  const post = usePostConfig()
  const pushToTalk = usePushToTalkKey()
  const offline = useOfflineService(['brain'])
  const [listening, setListening] = useState(false)
  const [name, setName] = useState('')
  const confirmed = config.data
  const shown = post.isPending && confirmed ? { ...confirmed, ...post.variables, knobs: { ...confirmed.knobs, ...post.variables?.knobs } } : confirmed
  const disabled = !confirmed || offline === 'brain'

  useEffect(() => setName(confirmed?.player ?? ''), [confirmed?.player])

  useEffect(() => {
    if (!listening) return
    const onKey = (event: KeyboardEvent) => {
      event.preventDefault()
      if (event.key !== 'Escape') setPushToTalkKey(keyLabel(event))
      setListening(false)
    }
    window.addEventListener('keydown', onKey, { once: true })
    return () => window.removeEventListener('keydown', onKey)
  }, [listening])

  const save = (update: ConfigUpdate) => post.mutate(update)
  const preset = PRESETS.find((candidate) => candidate.level === shown?.difficulty) ?? PRESETS[2]
  const knob = (key: KnobKey): number => (shown?.knobs?.[key] as number | undefined) ?? preset[key]
  const saveKnob = (key: KnobKey, value: number) => save({ knobs: { ...confirmed?.knobs, [key]: value } as Knobs })
  const saveName = () => {
    const trimmed = name.trim()
    if (trimmed && trimmed !== confirmed?.player) save({ player: trimmed })
    else setName(confirmed?.player ?? '')
  }

  return (
    <Screen title="Controls">
      <ScreenBanner service={offline} line="Settings show what the bot last confirmed." />
      {!shown && config.isPending && (
        <div className="flex gap-12">
          <Skeleton className="h-[420px] grow basis-0 rounded-md" faint />
          <Skeleton className="h-[420px] w-[380px] rounded-md" faint />
        </div>
      )}
      {shown && (
        <div className="flex items-start gap-12">
          <div className="flex grow basis-0 flex-col gap-[36px]">
            <section className="flex flex-col gap-4 border-t-2 border-solid border-t-primary pt-4">
              <div className="flex items-baseline justify-between">
                <h2 className="text-[18px] leading-[22px] font-bold text-text">Difficulty</h2>
                <span className="text-sm leading-[18px] text-text-muted">Presets set the three sliders below. Changes apply from the next match.</span>
              </div>
              <div className="flex gap-2">
                {PRESETS.map((item, index) => {
                  const current = item.level === shown.difficulty
                  return (
                    <button
                      key={item.level}
                      type="button"
                      aria-pressed={current}
                      disabled={disabled}
                      onClick={() =>
                        save({
                          difficulty: item.level,
                          knobs: {
                            ...confirmed?.knobs,
                            reaction_delay_frames: item.reaction_delay_frames,
                            punish_accuracy: item.punish_accuracy,
                            exploit_weight: item.exploit_weight
                          }
                        })
                      }
                      className={`focus-ring flex h-[76px] basis-0 flex-col justify-center gap-[2px] rounded-sm border-[1.5px] border-solid px-[14px] text-left disabled:opacity-60 ${GROW[index]} ${
                        current ? 'border-primary bg-primary text-overlay-text' : 'border-[#1D1B1633] text-text'
                      }`}
                    >
                      <span className="text-[22px] leading-[26px] font-[900]">{item.level}</span>
                      <span className={`text-base/sm ${current ? 'font-bold' : 'font-medium'}`}>{item.name}</span>
                    </button>
                  )
                })}
              </div>
            </section>
            <div className="flex flex-col gap-8">
              <KnobSlider label="Reaction delay" knob="reaction_delay_frames" value={knob('reaction_delay_frames')} low="30 frames, slow" high="6 frames, fast" format={(value) => `${Math.round(value)} frames`} disabled={disabled} onSave={saveKnob} />
              <KnobSlider label="Punish accuracy" knob="punish_accuracy" value={knob('punish_accuracy')} low="Misses most punishes" high="Punishes everything" format={(value) => `${Math.round(value * 100)}%`} disabled={disabled} onSave={saveKnob} />
              <KnobSlider label="Exploit weight" knob="exploit_weight" value={knob('exploit_weight')} low="Plays honest" high="Hunts your habits" format={(value) => `${Math.round(value * 100)}%`} disabled={disabled} onSave={saveKnob} />
            </div>
            {post.isError && <p className="text-base/sm text-text-muted">Couldn't save. {post.error.message}</p>}
          </div>
          <section className="flex w-[380px] shrink-0 flex-col gap-[20px] border-t-2 border-solid border-t-primary pt-4">
            <h2 className="text-[18px] leading-[22px] font-bold text-text">Match</h2>
            <label className="flex flex-col gap-2">
              <span className="text-sm leading-[18px] font-medium text-text-muted">Bot character</span>
              <Select size="field" value={shown.bot_character} disabled={disabled} onChange={(event) => save({ bot_character: event.currentTarget.value as Character })}>
                {CHARACTERS.map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </Select>
            </label>
            <label className="flex flex-col gap-2">
              <span className="text-sm leading-[18px] font-medium text-text-muted">Player name</span>
              <input
                value={name}
                disabled={disabled}
                onChange={(event) => setName(event.currentTarget.value)}
                onBlur={saveName}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') saveName()
                }}
                className="focus-ring h-12 rounded-sm border-[1.5px] border-solid border-[#1D1B1640] bg-surface px-[14px] text-base/sm text-text disabled:opacity-60"
              />
            </label>
            <div className="flex flex-col pt-1">
              <div className="flex items-center gap-4 border-t border-solid border-t-[#1D1B161F] py-[14px]">
                <div className="flex grow basis-0 flex-col gap-[2px]">
                  <span className="text-base/sm font-bold text-text">Demo mode</span>
                  <span className="text-sm/sm text-text-muted">Same seed and habits every run, for the booth</span>
                </div>
                <Toggle label="Demo mode" checked={Boolean(shown.demo_mode)} disabled={disabled} onChange={(checked) => save({ demo_mode: checked })} />
              </div>
              <div className="flex items-center gap-4 border-t border-solid border-t-[#1D1B161F] py-[14px]">
                <div className="flex grow basis-0 flex-col gap-[2px]">
                  <span className="text-base/sm font-bold text-text">Coach voice</span>
                  <span className="text-sm/sm text-text-muted">Speaks between rounds and in the Coach tab</span>
                </div>
                <Toggle label="Coach voice" checked={Boolean(shown.voice)} disabled={disabled} onChange={(checked) => save({ voice: checked })} />
              </div>
              <div className="flex items-center gap-4 border-y border-solid border-y-[#1D1B161F] py-[14px]">
                <span className="grow basis-0 text-base/sm font-bold text-text">Push-to-talk key</span>
                <KeyCap>{listening ? '…' : pushToTalk}</KeyCap>
                <TextButton onClick={() => setListening(true)}>{listening ? 'Press a key' : 'Change'}</TextButton>
              </div>
            </div>
          </section>
        </div>
      )}
    </Screen>
  )
}
