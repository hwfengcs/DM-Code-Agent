/**
 * 条目流 → 对话轮次。**展示层纯函数**，由 `turns.test.ts` 覆盖。
 *
 * 边界与 `entries.ts` 一致：这里只做分组和取值，任何「结论」（失败阶段、健康度、
 * 验证缺口）仍然由后端 `dm_agent.tracing` 算好送过来。
 *
 * 为什么对话视图不另存一份状态：一份 append-only 的会话日志已经完整表达了多轮
 * 对话——`run_start` 是用户发的那一句，中间的 step / tool_call 是 agent 干的活，
 * `run_end` 是它的回答。从条目推导轮次意味着**实时看到的和事后审计到的必然一致**，
 * 而且历史会话不需要第二套渲染器就能以对话形式打开。
 */
import type { SessionEntry } from './types'
import { actionOf, isFailureEntry, stringField } from './entries'

export interface ConversationTurnView {
  /** 从 1 开始的轮次序号。 */
  index: number
  /** 用户这一轮说了什么（`run_start.task`）。 */
  task: string
  /** 这一轮的全部条目，含 `run_start` / `run_end` 本身。 */
  entries: SessionEntry[]
  /** 执行过程条目（step / tool_call / replan / critic_review / 各类错误）。 */
  activity: SessionEntry[]
  /** agent 的最终回答；未结束时为空串。 */
  answer: string
  /** `run_end.status`；未结束时为空串。 */
  status: string
  /** 这一轮还在跑（没有 `run_end`）。 */
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
 * 需要逐条核对原文时右侧审计抽屉仍能看到全部条目。 */
const ACTIVITY_EVENTS = new Set([
  'plan',
  'step',
  'tool_call',
  'replan',
  'critic_review',
  'compaction',
  'guard_block',
  'truncation',
  'parse_error',
  'llm_error',
  'plan_error',
  'run_error',
  'circuit_breaker',
  'hook_error',
])

/**
 * 把条目流切成轮次。
 *
 * `run_start` 之前的条目（`runtime`、扩展诊断等）属于「会话建立」阶段，不归任何
 * 一轮——它们由调用方决定要不要显示，这里直接丢弃，免得第一轮凭空多出一堆噪音。
 */
export function splitTurns(entries: SessionEntry[]): ConversationTurnView[] {
  const turns: ConversationTurnView[] = []
  let current: ConversationTurnView | null = null

  for (const entry of entries) {
    if (entry.event === 'run_start') {
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

    if (entry.event === 'run_end') {
      current.answer = stringField(entry, 'final_answer')
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
    default:
      return stringField(entry, 'error') || stringField(entry, 'message') || stringField(entry, 'observation')
  }
}

/** 执行过程里某一条的标题：优先显示动作名，其次事件名。 */
export function labelActivityEntry(entry: SessionEntry): string {
  return actionOf(entry) || entry.event
}

/**
 * 这份日志能不能当成对话来读。
 *
 * 判据只有一条：有没有 `run_start`。没有的话（极老的 1.x trace、或只含 checkpoint
 * 条目的文件）就退回执行链视图，而不是渲染出一个空对话。
 */
export function looksLikeConversation(entries: SessionEntry[]): boolean {
  return entries.some((entry) => entry.event === 'run_start')
}
