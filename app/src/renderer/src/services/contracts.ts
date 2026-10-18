export type Character = 'devil_jin' | 'kazuya' | 'king' | 'shaheen' | 'unknown'

export type PlayerSlot = 0 | 1

export type HitLevel = 'none' | 'high' | 'mid' | 'low' | 'special_low' | 'throw'

export type EventKind =
  | 'round_start'
  | 'round_end'
  | 'hit'
  | 'counter_hit'
  | 'block'
  | 'whiff'
  | 'throw'
  | 'throw_break'
  | 'knockdown'
  | 'wakeup'
  | 'heat_activate'
  | 'rage_art'
  | 'side_switch'
  | 'decision_point'

export type DistanceBucket = 'point_blank' | 'close' | 'mid' | 'far' | 'very_far'

export type StateSituation =
  | 'neutral'
  | 'pressure'
  | 'defense'
  | 'punish_window'
  | 'combo'
  | 'knockdown'
  | 'wakeup'
  | 'throw'
  | 'round_over'

export type ThrowBreak = 'none' | 'press_1' | 'press_2' | 'press_12'

export type Direction = 'n' | 'f' | 'b' | 'd' | 'u' | 'df' | 'db' | 'uf' | 'ub'

export type Button = '1' | '2' | '3' | '4' | 'heat' | 'rage'

export interface PlayerState {
  slot: PlayerSlot
  character_id: number
  character: Character
  health: number
  recoverable_limit?: number
  max_health: number
  x: number
  y: number
  z: number
  facing?: number
  side: PlayerSlot
  move_id: number
  frame_in_move: number
  move_total: number
  free_movement: boolean
  hit_level: HitLevel
  hit_reaction: number
  status?: number
  basic_state?: number
  being_thrown: ThrowBreak
  throw_escaped?: boolean
  heat_gauge?: number
  heat_active?: boolean
  heat_used?: boolean
  rage_active?: boolean
  power_crush?: boolean
  first_active?: number
  last_active?: number
  first_airborne?: number
  last_airborne?: number
  dir_held?: Direction
  buttons_held?: Button[]
  buttons_pressed?: Button[]
}

export interface DerivedState {
  distance_mm: number
  distance_bucket: DistanceBucket
  frame_advantage?: number | null
  situation: StateSituation
  bearing_deg?: number
  timer_s?: number
}

export interface GameState {
  t: 'state'
  session_id: string
  frame: number
  round: number
  human_slot: PlayerSlot
  players: [PlayerState, PlayerState]
  derived: DerivedState
}

export interface GameEvent {
  t: 'event'
  session_id: string
  frame: number
  round: number
  kind: EventKind
  actor?: PlayerSlot
  target?: PlayerSlot
  move_id?: number
  hit_level?: HitLevel
  frame_advantage?: number | null
  damage?: number
  situation?: string
  action?: string
  detail?: Record<string, unknown>
}

export interface SessionRound {
  round: number
  winner: number | null
  start_frame?: number
  end_frame?: number
}

export interface SessionMeta {
  session_id: string
  started_at: string
  ended_at?: string | null
  game_version?: '3.02.02'
  mode?: 'practice' | 'versus' | 'synthetic'
  stage?: string
  player: string
  human_slot: PlayerSlot
  human_character: Character
  bot_character: Character
  difficulty: number
  rounds: SessionRound[]
  result?: string
  recording?: string
}

export interface TopHabit {
  situation: string
  action: string
  p: number
  n: number
  mastery?: number
  fixed?: boolean
}

export interface RoundMoment {
  frame: number
  kind: EventKind
  move_id?: number
  damage?: number
  situation?: string
}

export interface RoundSummary {
  t: 'round_summary'
  session_id: string
  round: number
  frame?: number
  winner: PlayerSlot | null
  human_slot: PlayerSlot
  human_character?: Character
  bot_character?: Character
  difficulty?: number
  human_damage_taken: number
  bot_damage_taken: number
  top_habits: TopHabit[]
  biggest_moments: RoundMoment[]
  exploited?: string[]
  newly_fixed?: string[]
  regressed?: string[]
}

export interface ReportHabit {
  situation: string
  action?: string
  count: number
  p: number
  mastery?: number
  min_change: string
  moments?: number[]
}

export interface DecisionOption {
  name: string
  command?: string
  p: number
}

export interface DecisionPoint {
  frame: number
  round: number
  situation: string
  actual: string
  best: string
  options: DecisionOption[]
  why?: string
  cost?: number
  good?: boolean
}

export interface Report {
  session_id: string
  generated_at?: string
  result: string
  habits: ReportHabit[]
  decision_points: DecisionPoint[]
  went_well: string[]
  drills: string[]
}

export interface HabitEstimate {
  p: number
  n: number
  mastery?: number
  fixed?: boolean
}

export interface LearningRound {
  t?: 'learning_round'
  session_id?: string
  round: number
  prediction_accuracy: number | null
  habits: Record<string, HabitEstimate>
  bandit?: Record<string, Record<string, number>>
  player_changed?: boolean
}

export interface LearningMetrics {
  session_id: string
  rounds: LearningRound[]
  time_to_detect?: Record<string, number>
  time_to_mastery?: Record<string, number>
  finetune?: {
    before?: number | null
    after?: number | null
  }
}

export interface MasteryState {
  p_learned: number
  observations: number
  fixed: boolean
  last_retest?: string | null
}

export interface Profile {
  player: string
  character: Character
  sessions: number
  habits: Record<string, Record<string, [number, number]>>
  mastery: Record<string, MasteryState>
  bandits: Record<string, Record<string, [number, number]>>
  predictor?: string | null
  history?: unknown[]
}

export type OptionClass = 'mid' | 'low' | 'throw' | 'launcher' | 'backdash' | 'sidestep' | 'approach' | 'wait'

export interface TargetHabit {
  situation: string
  action: string
  weight: number
}

export interface GamePlan {
  aggression: number
  risk_tolerance: number
  target_habits: TargetHabit[]
  option_weights: Partial<Record<OptionClass, number>>
  wall_strategy?: 'none' | 'carry' | 'avoid'
  note: string
}

export interface PlanRecord extends GamePlan {
  t: 'plan'
  session_id: string
  round: number
  frame: number
}

export interface TacticalRecord {
  t: 'tactical'
  session_id: string
  round: number
  frame: number
  frame_asked?: number
  options?: unknown
  chosen?: unknown
  probabilities?: unknown
  source?: 'laya' | 'default' | 'habit'
}

export interface Knobs {
  reaction_delay_frames?: number
  frame_perfect_chance?: number
  punish_accuracy?: number
  exploit_weight?: number
  combo_set?: 'short' | 'short_plus_optimal' | 'optimal'
  movement_set?: 'basic' | 'sidestep' | 'character' | 'full'
  mixup_temperature?: number
  execution_error?: number
}

export interface Config {
  difficulty: number
  knobs?: Knobs
  bot_character: Character
  player: string
  demo_mode?: boolean
  voice?: boolean
}

export type ConfigUpdate = Partial<Config>

export interface Health {
  ok: boolean
  service: string
  version: string
}

export type CoachSeverity = 'info' | 'warn' | 'praise'

export interface CoachMessage {
  t: 'coach'
  session_id: string
  round: number
  text: string
  severity: CoachSeverity
}

export interface ChatTurn {
  role: string
  text: string
}

export interface ChatRequest {
  session_id: string
  player: string
  message: string
  history: ChatTurn[]
}

export interface ChatCitation {
  frame: number
  round: number
}

export interface ChatReply {
  text: string
  citations: ChatCitation[]
}

export interface StatsTotals {
  damage_taken_by_situation: Record<string, number>
  punish_rate: number | null
  throw_break_rate: number | null
  low_block_rate: number | null
  counter_hits_taken: number
  counter_hits_given: number
  avg_adv_after_block: number | null
}

export interface StatsRound extends StatsTotals {
  round: number
}

export interface SessionStats {
  session_id: string
  rounds: StatsRound[]
  totals: StatsTotals
}

export interface TrendPoint {
  session_id: string
  started_at: string
  values: Record<string, number | null>
}

export interface Trends {
  player: string
  character: string
  series: TrendPoint[]
}

export type InsightMetricKey = 'low_defense' | 'throw_defense' | 'punish_conversion'

export type InsightMetricState = 'observed' | 'early_signal' | 'no_opportunities' | 'invalid'

export interface InsightLocation {
  line: number
  round: number
  frame: number | null
}

export interface InsightEvent {
  kind: string
  actor?: number
  target?: number
  damage?: number
  hit_level?: string
  move_id?: number | string
  frame_advantage?: number
}

export interface InsightEvidence {
  opportunity: InsightLocation
  response: InsightLocation | null
  outcome: 'success' | 'failure'
  event: InsightEvent
}

export interface InsightMetric {
  label: string
  successes: number
  opportunities: number
  failures: number | null
  value: number | null
  state: InsightMetricState
  estimated: boolean
  evidence_total: number
  evidence: InsightEvidence[]
}

export interface InsightHabit {
  first_detected_round: number | null
  first_fixed_round: number | null
  current_round: number
  fixed: boolean | null
  regressed: boolean
  last_regressed_round: number | null
}

export interface InsightMoment {
  reference: InsightLocation
  metrics: InsightMetricKey[]
  outcome: 'success' | 'failure' | 'mixed' | 'damage'
  response: InsightLocation | null
  event: InsightEvent
  metric_outcomes: Partial<Record<InsightMetricKey, { outcome: 'success' | 'failure'; response: InsightLocation | null }>>
}

export interface InsightsV1 {
  format_version: 1
  snapshot_id: string
  session_id: string
  synthetic: boolean | null
  recording_sha256: string | null
  freshness: {
    latest_completed_round: number | null
    latest_recording_round: number | null
    latest_learning_round: number | null
    pending_learning_rounds: number[]
    learning_ahead_rounds: number[]
  }
  quality: 'observed' | 'pending' | 'invalid'
  metrics: Record<InsightMetricKey, InsightMetric>
  focus: {
    mode: 'automatic' | 'manual'
    metric: InsightMetricKey | null
    state: 'observed' | 'early_signal' | null
    reason: string
    action: string | null
    action_reviewed: boolean
    min_opportunities?: number
  }
  habits: Record<string, InsightHabit>
  moments: InsightMoment[]
  moments_total: number
}
