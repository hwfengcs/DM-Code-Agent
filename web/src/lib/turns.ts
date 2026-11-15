/**
 * 条目流 → 对话轮次。**展示层纯函数**，由 `turns.test.ts` 覆盖。
 *
 * 边界与 `entries.ts` 一致：这里只做分组和取值，任何「结论」（失败阶段、健康度、
 * 验证缺口）仍然由后端 `dm_agent.tracing` 算好送过来。
 *
 * 为什么对话视图不另存一份状态：一份 append-only 的会话日志已经完整表达了多轮
 * 对话——`turn_start` / `turn_end` 标记用户轮次，中间的 step / tool_call 是 agent 干的活。
 * 旧日志回退到 `run_start` / `run_end`。从条目推导轮次意味着实时与历史视图口径一致，
 * 而且历史会话不需要第二套渲染器就能以对话形式打开。
 */
import type { SessionEntry } from './types'
import { actionOf, isFailureEntry, stringField } from './entries'

export interface ConversationTurnView {
  /** 从 1 开始的轮次序号。 */
  index: number
  /** 用户这一轮说了什么（`turn_start.task`，旧日志取 `run_start.task`）。 */
  task: string
  /** 这一轮的全部条目，含轮次边界与内部运行。 */
  entries: SessionEntry[]
  /** 执行过程条目（step / tool_call / replan / critic_review / 各类错误）。 */
  activity: SessionEntry[]
  /** agent 的最终回答；未结束时为空串。 */
  answer: string
  /** `turn_end.status`；旧日志取 `run_end.status`。 */
  status: string
  /** 这一轮还在跑（没有对应的结束记录）。 */
  running: boolean
  /** 过程里出现过失败条目。用于在收起状态下也能看见「这轮不顺」。 */
  failed: boolean
  toolCallCount: number
  stepCount: number
  replanCount: number
  startedAt: string
  finishedAt: string
}

/** 会被算进「执行过程」的事件。刻意不含 `message`——那是对话历史的原始载体，
 * 在对话视图里由 `run_start` / `run_end` 表达，重复列出来只会让过程变噪音。
 * 需要逐条核对原文时右侧审计抽屉仍能看到全部条目。
 *
 * 事件名必须与后端写出的一字不差：守卫拦截是 `edit_guard`（`core/guards.py`），
 * 观察截断是 `observation_truncated`（`core/observation.py`）。`critic_review` 与
 * `circuit_breaker` 对应的模块已在 v2.1 移除，保留是为了老日志仍能照常显示。 */
const ACTIVITY_EVENTS = new Set([
  'plan',
  'step',
  'tool_call',
  'replan',
  'critic_review',
  'compaction',
  'edit_guard',
  'observation_truncated',
  'parse_error',
  'llm_error',
  'plan_error',
  'run_error',
  'circuit_breaker',
  'hook_error',
  'completion_rejected',
])

/** `edit_guard.reason` 的人话。取值来自 `memory/context_budget.py` 的 `FileLedger.check_edit`。 */
const EDIT_GUARD_REASONS: Record<string, string> = {
  never_read: '本次运行里还没读过',
  stale_read: '上次读取之后文件又被改写',
}

/**
 * 把条目流切成轮次。
 *
 * 轮次开始之前的条目（`runtime`、扩展诊断等）属于「会话建立」阶段，不归任何
 * 一轮——它们由调用方决定要不要显示，这里直接丢弃，免得第一轮凭空多出一堆噪音。
 */
export function splitTurns(entries: SessionEntry[], active = true): ConversationTurnView[] {
  const turns: ConversationTurnView[] = []
  let current: ConversationTurnView | null = null
  let explicit = false

  for (const entry of entries) {
    if (entry.event === 'conversation_start') explicit = true
    if (entry.event === 'turn_start') explicit = true
    if (entry.event === 'turn_start' || (!explicit && entry.event === 'run_start')) {
      current = {
        index: turns.length + 1,
        task: stringField(entry, 'task'),
        entries: [entry],
        activity: [],
        answer: '',
        status: '',
        running: true,
        failed: false,
        toolCallCount: 0,
        stepCount: 0,
        replanCount: 0,
        startedAt: entry.timestamp,
        finishedAt: '',
      }
      turns.push(current)
      continue
    }
    if (current === null) continue

    current.entries.push(entry)
    if (isFailureEntry(entry)) current.failed = true

    if (explicit && entry.event === 'run_start') {
      if (!current.task) current.task = stringField(entry, 'task')
      current.answer = ''
      current.status = ''
    }
    if (entry.event === 'run_end') {
      current.answer = stringField(entry, 'final_answer')
      if (explicit) continue
      current.status = stringField(entry, 'status')
      current.running = false
      current.finishedAt = entry.timestamp
      continue
    }
    if (entry.event === 'turn_end') {
      current.status = stringField(entry, 'status')
      current.running = false
      current.finishedAt = entry.timestamp
      continue
    }
    if (ACTIVITY_EVENTS.has(entry.event)) {
      current.activity.push(entry)
      if (entry.event === 'tool_call') current.toolCallCount += 1
      if (entry.event === 'step') current.stepCount += 1
      if (entry.event === 'replan') current.replanCount += 1
    }
  }
  for (const turn of turns) {
    if (turn.running && (!active || turn !== turns.at(-1) || turn.entries.some((entry) => entry.event === 'conversation_end' || entry.event === 'turn_end'))) {
      turn.running = false
      turn.status = 'interrupted'
    }
  }
  return turns
}

/** 收起状态下那一行摘要：「3 步 · 2 次工具调用 · 1 次重规划」。 */
export function describeActivity(turn: ConversationTurnView): string {
  const parts: string[] = []
  if (turn.stepCount) parts.push(`${turn.stepCount} 步`)
  if (turn.toolCallCount) parts.push(`${turn.toolCallCount} 次工具调用`)
  if (turn.replanCount) parts.push(`${turn.replanCount} 次重规划`)
  if (parts.length === 0) return turn.activity.length ? `${turn.activity.length} 条记录` : ''
  return parts.join(' · ')
}

/** 执行过程里某一条的一行说明。挑该事件最有信息量的字段，而不是无脑 stringify。 */
export function describeActivityEntry(entry: SessionEntry): string {
  switch (entry.event) {
    case 'plan': {
      const steps = entry.payload.steps
      return Array.isArray(steps) ? `生成了 ${steps.length} 步计划` : '生成计划'
    }
    case 'step':
      return stringField(entry, 'observation') || stringField(entry, 'thought')
    case 'tool_call':
      return stringField(entry, 'observation')
    case 'replan':
      return stringField(entry, 'reason') || '触发重规划'
    case 'critic_review':
      return stringField(entry, 'reason') || stringField(entry, 'verdict')
    case 'compaction': {
      const before = entry.payload.estimated_tokens_before
      const after = entry.payload.estimated_tokens_after
      if (typeof before === 'number' && typeof after === 'number') {
        return `上下文折叠 ${before} → ${after} tokens（原文仍在）`
      }
      return '上下文折叠（原文仍在）'
    }
    case 'edit_guard': {
      const reason = stringField(entry, 'reason')
      const detail = EDIT_GUARD_REASONS[reason] ?? reason
      const suffix = detail ? `（${detail}）` : ''
      return `编辑被拦下：${stringField(entry, 'path')}${suffix}`
    }
    case 'observation_truncated': {
      const original = entry.payload.original_chars
      const kept = entry.payload.kept_chars
      const tool = actionOf(entry)
      const subject = tool ? `${tool} 的观察被截断` : '观察被截断'
      if (typeof original === 'number' && typeof kept === 'number') {
        return `${subject}：${original} → ${kept} 字符`
      }
      return subject
    }
    default:
      return stringField(entry, 'error') || stringField(entry, 'message') || stringField(entry, 'observation')
  }
}

/**
 * 执行过程里某一条的标题：步骤与工具调用显示动作名，其余显示事件名。
 *
 * 只认这两种事件，是因为别的事件也可能带 `action` 字段却不是一次动作——
 * `observation_truncated.action` 说的是「被截断的是哪个工具的观察」，拿它当标题
 * 会让一条截断记录看起来像又调了一次工具。
 */
export function labelActivityEntry(entry: SessionEntry): string {
  if (entry.event === 'step' || entry.event === 'tool_call') return actionOf(entry) || entry.event
  return entry.event
}

/**
 * 这份日志能不能当成对话来读。
 *
 * 判据是有没有 `turn_start` 或 `run_start`。没有的话（极老的 1.x trace、或只含 checkpoint
 * 条目的文件）就退回执行链视图，而不是渲染出一个空对话。
 */
export function looksLikeConversation(entries: SessionEntry[]): boolean {
  return entries.some((entry) => entry.event === 'turn_start' || entry.event === 'run_start')
}
