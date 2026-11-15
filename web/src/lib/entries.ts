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
  // 截断的事件名以后端为准：core/observation.py 写的是 observation_truncated。
  if (event.includes('guard') || event.includes('breaker') || event === 'observation_truncated') {
    return 'guard'
  }
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

// --- 格式化 ---------------------------------------------------------------

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  // 每一档都按「取整之后」的值分档，否则边界上会写出 1000ms、60.0s、1m60s 这类没进位的值。
  const millis = Math.round(seconds * 1000)
  if (millis < 1000) return `${millis}ms`
  if (seconds < 59.95) return `${seconds.toFixed(1)}s`
  const total = Math.round(seconds)
  return `${Math.floor(total / 60)}m${total % 60}s`
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

/**
 * 幻觉信号的键 → 中文标签。键名的真相源是后端 `tracing/analysis.py` 的
 * `_hallucination_signals`；这里少一个，诊断面板上就会露出原始英文键。
 */
const HALLUCINATION_LABELS: Record<string, string> = {
  edit_without_read_count: '未读先改',
  edit_guard_blocks: '被守卫拦下',
  truncation_hits: '观察被截断',
  truncation_hit_rate: '截断命中率',
  missing_path_reference_count: '引用了不存在的路径',
}

/** 看不懂的键原样返回，不猜。 */
export function describeHallucinationSignal(key: string): string {
  return HALLUCINATION_LABELS[key] ?? key
}

/** 信号值的展示文本：命中率是 0–1 的比例，按百分比写；其余是计数。 */
export function formatHallucinationValue(key: string, value: number): string {
  if (key === 'truncation_hit_rate' && typeof value === 'number') {
    return `${Number((value * 100).toFixed(1))}%`
  }
  return String(value)
}

/**
 * 把后端送来的一行补成合法的 `SessionEntry`。
 *
 * 后端读侧只保证「每行是 JSON 对象、payload 若有则是对象」并补齐空缺的 id。sessions
 * 目录里一份不是会话日志的 JSONL（例如 predictions 文件）因此会原样送到前端：没有
 * `event`，也没有 `payload`。本文件的纯函数与各视图都按 `SessionEntry` 的类型直接
 * 取值，缺了字段就在渲染途中抛 TypeError，而前端没有 ErrorBoundary——整个控制台白屏。
 * 所以在数据入口（`api.ts`）补一次：只补缺、不改已有的值，多出来的字段原样留着。
 */
export function normalizeEntry(raw: unknown): SessionEntry {
  const source = isRecord(raw) ? raw : {}
  return {
    ...source,
    id: textField(source.id),
    parent_id: textField(source.parent_id),
    timestamp: textField(source.timestamp),
    run_id: textField(source.run_id),
    event: textField(source.event),
    payload: isRecord(source.payload) ? source.payload : {},
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** 字符串原样返回；数字转成文本（外来 JSONL 里常见数字 id）；其余当作缺失。 */
function textField(value: unknown): string {
  if (typeof value === 'string') return value
  return typeof value === 'number' ? String(value) : ''
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function numberOrNull(value: unknown): number | null {
  return typeof value === 'number' ? value : null
}
