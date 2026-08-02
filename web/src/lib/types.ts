/**
 * 与后端 JSON 契约一一对应的类型。
 *
 * 这些形状的**唯一真相源在 Python 侧**（`dm_agent/tracing/summary.py` 与
 * `analysis.py`）。这里只是把它们抄成 TypeScript 好拿到编辑器提示——
 * 前端不重算任何诊断结论，只负责渲染。
 */

/** 一条 append-only 会话条目。payload 的形状随 event 变化，故为 unknown。 */
export interface SessionEntry {
  id: string
  parent_id: string
  timestamp: string
  run_id: string
  event: string
  payload: Record<string, unknown>
}

export interface TraceHealth {
  score: number
  grade: 'good' | 'warning' | 'risky'
  issues: string[]
}

export interface SessionCard {
  name: string
  run_id: string
  task: string
  status: string
  provider: string | null
  model: string | null
  step_count: number
  event_count: number
  tool_call_count: number
  replan_count: number
  duration_seconds: number | null
  run_count: number
  health: TraceHealth
  size_bytes: number
  modified: number
}

export interface SessionListResponse {
  sessions: SessionCard[]
  errors: { name: string; error: string }[]
  aggregate: {
    total: number
    unreadable: number
    by_status: Record<string, number>
    by_health: Record<string, number>
  }
}

export interface PlanStep {
  step_number: number | null
  action: string | null
  reason: string | null
  completed: boolean
}

export interface StepPayload {
  step_number?: number
  action?: string
  thought?: string
  observation?: string
  action_input?: unknown
}

export interface SessionSummary {
  run_id: string
  schema_version: string | null
  task: string
  status: string
  final_answer: string
  duration_seconds: number | null
  provider: string | null
  model: string | null
  base_url: string | null
  event_count: number
  step_count: number
  tool_call_count: number
  replan_count: number
  plan_steps: PlanStep[]
  steps: StepPayload[]
}

export interface VerificationAnalysis {
  actions: { step_number: number; action: string }[]
  count: number
  finish_step: number | null
  /** 是否在宣布完成**之前**跑过验证。 */
  before_finish: boolean
  /** 成功但没验证——「任务成功 ≠ 过程健康」的那条信号。 */
  gap: boolean
}

export interface SessionAnalysis {
  run_id: string
  task: string
  status: string
  primary_failure_stage: string
  final_failure_stage: string
  signals: string[]
  recovery: {
    failure_event_count: number
    first_failure_step: number | null
    first_failure_event: string | null
    replan_count: number
    replanned_after_failure: boolean
    recovered: boolean
  }
  verification: VerificationAnalysis
  hallucination_signals: Record<string, number>
  metadata_counters: Record<string, number>
  trace_health: TraceHealth
}

export interface EntriesResponse {
  name: string
  total: number
  offset: number
  limit: number
  entries: SessionEntry[]
}

export interface DiffResponse {
  a: string
  b: string
  diff: Record<string, unknown>
}

export interface ForkResponse {
  mode: string
  source: string
  output: string
  forked_from_entry_id: string
  entry_count: number
  resumable_checkpoint_entry_id: string
  resumable_step_number: number | null
}

export type RunStatus =
  | 'running'
  | 'idle'
  | 'completed'
  | 'incomplete'
  | 'failed'
  | 'cancelled'

export interface RunRecord {
  run_id: string
  task: string
  session: string
  status: RunStatus
  /** 会话日志 run_end 里 agent 自己判定的状态；退出码 0 ≠ agent 做完了。 */
  agent_status: string
  started_at: number
  finished_at: number | null
  exit_code: number | null
  cancelled: boolean
  error: string
  pid: number
  kind?: 'run' | 'conversation'
}

/** 对话里的一轮。「跑完没有」不在这里——那个由 `completed_turns` 从会话日志现算。 */
export interface ConversationTurn {
  index: number
  task: string
  submitted_at: number
}

/**
 * 一个长驻对话子进程的服务端视图。
 *
 * `status` 的语义与一次性运行不同：`idle` 表示对话开着但没有轮次在跑，
 * `running` 才表示当前有一轮在执行。
 */
export interface ConversationRecord extends RunRecord {
  kind: 'conversation'
  turns: ConversationTurn[]
  submitted_turns: number
  completed_turns: number
  busy: boolean
  last_activity: number
}

export interface CapabilityInfo {
  flag: string
  key: string
  kind: 'bool' | 'int' | 'float'
  default: boolean | number
  category: 'guardrail' | 'behavior' | 'tuning'
  label: string
  help: string
}

export interface MetaResponse {
  version: string
  server: {
    read_only: boolean
    auth_required: boolean
    /**
     * 工作区的**完整绝对路径**。
     *
     * 不要直接渲染它——整条 `C:\Users\...\project` 怼在界面上既难看又没信息量。
     * 界面一律用 `workspace_name`（或 `lib/paths.ts` 的 `workspaceName()`）。
     */
    workspace: string
    /** 工作区目录名，界面上显示的就是这个。 */
    workspace_name: string
    sessions_dir_name: string
  }
  providers: {
    name: string
    model: string
    base_url: string
    env_key: string
    api_key_present: boolean
  }[]
  capabilities: CapabilityInfo[]
  tools: { name: string; description: string }[]
}
