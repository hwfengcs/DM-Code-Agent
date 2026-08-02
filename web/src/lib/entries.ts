/**
 * 会话条目的**展示层**纯函数。
 *
 * 边界很重要：这里只做分组、归类、格式化。任何「结论」（失败阶段、健康度、
 * 验证缺口、行为 diff）一律由后端的 `dm_agent.tracing` 算好送过来，前端不重算——
 * 否则就有了第二套实现，两边迟早漂移。
 *
 * 本文件全部是纯函数，由 `entries.test.ts` 覆盖。
 */
import type { SessionEntry } from './types'

export type EventKind =
  | 'lifecycle'
  | 'plan'
  | 'llm'
  | 'tool'
  | 'step'
  | 'message'
  | 'compaction'
  | 'replan'
  | 'critic'
  | 'guard'
  | 'failure'
  | 'other'

/** 事件名 → 展示归类。用于时间线的颜色、图标与筛选。 */
export function classifyEvent(entry: SessionEntry): EventKind {
  const event = entry.event
  if (event === 'run_start' || event === 'run_end' || event === 'runtime' || event === 'fork') {
    return 'lifecycle'
  }
  if (event === 'plan') return 'plan'
  if (event === 'llm_call') return 'llm'
  if (event === 'step') return 'step'
  if (event === 'message') return 'message'
  if (event === 'compaction') return 'compaction'
  if (event === 'replan') return 'replan'
  if (event === 'critic_review') return 'critic'
  if (event === 'checkpoint') return 'lifecycle'
  if (event.endsWith('_error') || event === 'run_error') return 'failure'
  if (event.includes('guard') || event.includes('breaker') || event === 'truncation') return 'guard'
  if (event === 'tool_call') return entry.payload.failed === true ? 'failure' : 'tool'
  return 'other'
}

/** 这条条目是否代表一次「出事了」。时间线用它决定要不要标红。 */
export function isFailureEntry(entry: SessionEntry): boolean {
  if (entry.event === 'tool_call') return entry.payload.failed === true
  if (entry.event === 'critic_review') return entry.payload.passed === false
  return (
    entry.event === 'parse_error' ||
    entry.event === 'llm_error' ||
    entry.event === 'plan_error' ||
    entry.event === 'run_error'
  )
}

export function stepNumberOf(entry: SessionEntry): number | null {
  const value = entry.payload.step_number
  return typeof value === 'number' ? value : null
}

export function actionOf(entry: SessionEntry): string {
  const value = entry.payload.action
  return typeof value === 'string' ? value : ''
}

export function stringField(entry: SessionEntry, key: string): string {
  const value = entry.payload[key]
  return typeof value === 'string' ? value : ''
}

/**
 * 一个 JSONL 可以连续记录多个 run。按 `run_start` 切段，供前端提示「这里有多段」
 * 并允许只看其中一段。第一个 `run_start` 之前的条目（如 `runtime`）归入第一段。
 */
export interface RunSegment {
  index: number
  runId: string
  startIndex: number
  endIndex: number
  task: string
}

export function splitRuns(entries: SessionEntry[]): RunSegment[] {
  const starts: number[] = []
  entries.forEach((entry, index) => {
    if (entry.event === 'run_start') starts.push(index)
  })
  if (starts.length === 0) {
    return entries.length
      ? [
          {
            index: 0,
            runId: entries[0]?.run_id ?? '',
            startIndex: 0,
            endIndex: entries.length - 1,
            task: '',
          },
        ]
      : []
  }
  return starts.map((start, order) => {
    // 首段从 0 开始，把 run_start 之前的 runtime 等条目一并纳入。
    const startIndex = order === 0 ? 0 : start
    const endIndex = order + 1 < starts.length ? (starts[order + 1] ?? entries.length) - 1 : entries.length - 1
    return {
      index: order,
      runId: entries[start]?.run_id ?? '',
      startIndex,
      endIndex,
      task: stringField(entries[start] as SessionEntry, 'task'),
    }
  })
}

/** 时间线的一组：一个步骤号下的全部条目。步骤号缺失的归到 `null` 组，按出现顺序穿插。 */
export interface StepGroup {
  stepNumber: number | null
  entries: SessionEntry[]
  action: string
  failed: boolean
}

export function groupByStep(entries: SessionEntry[]): StepGroup[] {
  const groups: StepGroup[] = []
  let current: StepGroup | null = null

  for (const entry of entries) {
    const step = stepNumberOf(entry)
    if (current === null || current.stepNumber !== step) {
      current = { stepNumber: step, entries: [], action: '', failed: false }
      groups.push(current)
    }
    current.entries.push(entry)
    // 组的标题动作取该组里 step 条目的 action，其次取 tool_call 的。
    if (entry.event === 'step' && actionOf(entry)) current.action = actionOf(entry)
    else if (!current.action && entry.event === 'tool_call') current.action = actionOf(entry)
    if (isFailureEntry(entry)) current.failed = true
  }
  return groups
}

/**
 * 折叠视图的数据。
 *
 * 本项目的核心卖点是「折叠只追加派生记录，原文一条不删」。要让这句话有说服力，
 * 就得把 compaction 条目和它**跳过**的那些 message 条目并排画出来——原文还在文件里，
 * 只是构造上下文时被跳过。
 */
export interface CompactionSpan {
  entry: SessionEntry
  /** 被折叠（构造上下文时跳过）的 message 条目 id。 */
  foldedIds: string[]
  /** 折叠后保留的第一条 message 条目 id。 */
  firstKeptId: string
  tokensBefore: number | null
  tokensAfter: number | null
  phase: string
  trigger: string
}

export function compactionSpans(entries: SessionEntry[]): CompactionSpan[] {
  return entries
    .filter((entry) => entry.event === 'compaction')
    .map((entry) => ({
      entry,
      foldedIds: stringArray(entry.payload.folded_entry_ids),
      firstKeptId: stringField(entry, 'first_kept_entry_id'),
      tokensBefore: numberOrNull(entry.payload.estimated_tokens_before),
      tokensAfter: numberOrNull(entry.payload.estimated_tokens_after),
      phase: stringField(entry, 'phase'),
      trigger: stringField(entry, 'trigger'),
    }))
}

/** 全部被折叠过的 message 条目 id。时间线据此把它们画成「已折叠但仍在案」。 */
export function foldedEntryIds(entries: SessionEntry[]): Set<string> {
  const folded = new Set<string>()
  for (const span of compactionSpans(entries)) {
    for (const id of span.foldedIds) folded.add(id)
  }
  return folded
}

export interface TreeNode {
  entry: SessionEntry
  children: TreeNode[]
  depth: number
}

/**
 * 按 parent_id 还原会话树。
 *
 * 正常情况下这是一条链；分叉出来的会话第一条 `fork` 会指回源会话的分叉点，
 * 那个 parent 在本文件里不存在，于是自然成为一个新根——正是想要的效果。
 */
export function buildTree(entries: SessionEntry[]): TreeNode[] {
  const nodes = new Map<string, TreeNode>()
  for (const entry of entries) {
    nodes.set(entry.id, { entry, children: [], depth: 0 })
  }
  const roots: TreeNode[] = []
  for (const entry of entries) {
    const node = nodes.get(entry.id)
    if (!node) continue
    const parent = entry.parent_id ? nodes.get(entry.parent_id) : undefined
    if (parent) {
      parent.children.push(node)
      node.depth = parent.depth + 1
    } else {
      roots.push(node)
    }
  }
  return roots
}

// --- 格式化 ---------------------------------------------------------------

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const minutes = Math.floor(seconds / 60)
  return `${minutes}m${Math.round(seconds % 60)}s`
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}

export function formatClock(timestamp: string): string {
  const parsed = new Date(timestamp)
  if (Number.isNaN(parsed.getTime())) return '—'
  return parsed.toLocaleTimeString('zh-CN', { hour12: false })
}

/** 会话列表里的「多久以前」。传入的是 Python `st_mtime`（秒）。 */
export function formatRelative(epochSeconds: number, now = Date.now()): string {
  const deltaSeconds = Math.max(0, now / 1000 - epochSeconds)
  if (deltaSeconds < 60) return '刚刚'
  if (deltaSeconds < 3600) return `${Math.floor(deltaSeconds / 60)} 分钟前`
  if (deltaSeconds < 86400) return `${Math.floor(deltaSeconds / 3600)} 小时前`
  if (deltaSeconds < 86400 * 30) return `${Math.floor(deltaSeconds / 86400)} 天前`
  return new Date(epochSeconds * 1000).toLocaleDateString('zh-CN')
}

/** 诊断信号 / 健康问题的中文说明。看不懂的原样返回，不猜。 */
export function describeIssue(issue: string): string {
  const table: Record<string, string> = {
    verification_gap: '宣布完成前没跑过任何验证',
    missing_run_start: '缺少 run_start，日志不完整',
    missing_run_end: '缺少 run_end，运行可能被中断',
    failure_without_replan: '出现失败但没有触发重规划',
    unrecovered_parse_errors: '解析错误未被恢复',
    unrecovered_tool_errors: '工具错误未被恢复',
    replanned_after_failure: '失败后触发了重规划',
    no_replan_after_failure: '失败后没有重规划',
  }
  if (table[issue]) return table[issue]
  const [prefix, detail] = issue.split(':')
  if (prefix === 'final_failure') return `最终失败在 ${detail} 阶段`
  if (prefix === 'primary_failure') return `首次失败在 ${detail} 阶段`
  return issue
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function numberOrNull(value: unknown): number | null {
  return typeof value === 'number' ? value : null
}
