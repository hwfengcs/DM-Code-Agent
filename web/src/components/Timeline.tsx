/**
 * 时间线：一次运行的全部条目，按步骤分组。
 *
 * 被折叠过的 message 条目会画成半透明并标「已折叠」——但**仍然在列**。
 * 这是本项目和别家最不一样的地方：折叠不删原文，所以事后还能逐条核对。
 */
import type { SessionEntry } from '../lib/types'
import {
  actionOf,
  classifyEvent,
  formatClock,
  groupByStep,
  isFailureEntry,
  stringField,
  type EventKind,
} from '../lib/entries'

const KIND_STYLE: Record<EventKind, { dot: string; label: string; text: string }> = {
  lifecycle: { dot: 'bg-scope-faint', label: '生命周期', text: 'text-scope-dim' },
  plan: { dot: 'bg-signal-plan', label: '计划', text: 'text-signal-plan' },
  llm: { dot: 'bg-signal-info/50', label: 'LLM', text: 'text-scope-dim' },
  tool: { dot: 'bg-signal-info', label: '工具', text: 'text-scope-text' },
  step: { dot: 'bg-scope-text', label: '步骤', text: 'text-scope-text' },
  message: { dot: 'bg-scope-line', label: '消息', text: 'text-scope-dim' },
  compaction: { dot: 'bg-signal-plan/70', label: '折叠', text: 'text-signal-plan' },
  replan: { dot: 'bg-signal-plan', label: '重规划', text: 'text-signal-plan' },
  critic: { dot: 'bg-signal-warn', label: 'Critic', text: 'text-signal-warn' },
  guard: { dot: 'bg-signal-warn', label: '守卫', text: 'text-signal-warn' },
  failure: { dot: 'bg-signal-risk', label: '失败', text: 'text-signal-risk' },
  other: { dot: 'bg-scope-line', label: '其他', text: 'text-scope-dim' },
}

export function Timeline({
  entries,
  foldedIds,
  selectedId,
  onSelect,
}: {
  entries: SessionEntry[]
  foldedIds: Set<string>
  selectedId: string | null
  onSelect: (entry: SessionEntry) => void
}) {
  const groups = groupByStep(entries)

  return (
    <ol className="divide-y divide-scope-line-soft/60">
      {groups.map((group, index) => (
        <li key={`${group.stepNumber ?? 'x'}-${index}`}>
          <div className="flex items-center gap-2 bg-scope-raised/40 px-3 py-1">
            <span className="meta-label">
              {group.stepNumber === null ? '运行级' : `步骤 ${group.stepNumber}`}
            </span>
            {group.action && (
              <span
                className={`font-mono text-xs ${group.failed ? 'text-signal-risk' : 'text-scope-text'}`}
              >
                {group.action}
              </span>
            )}
            {group.failed && <span className="chip border-signal-risk/40 text-signal-risk">失败</span>}
          </div>
          <ul>
            {group.entries.map((entry) => (
              <EntryRow
                key={entry.id}
                entry={entry}
                folded={foldedIds.has(entry.id)}
                selected={entry.id === selectedId}
                onSelect={onSelect}
              />
            ))}
          </ul>
        </li>
      ))}
    </ol>
  )
}

function EntryRow({
  entry,
  folded,
  selected,
  onSelect,
}: {
  entry: SessionEntry
  folded: boolean
  selected: boolean
  onSelect: (entry: SessionEntry) => void
}) {
  const kind = classifyEvent(entry)
  const style = KIND_STYLE[kind]
  const failed = isFailureEntry(entry)

  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(entry)}
        className={`focus-ring flex w-full items-start gap-2 px-3 py-1.5 text-left transition-colors ${
          selected ? 'bg-signal-info/10' : 'hover:bg-scope-raised/40'
        } ${folded ? 'opacity-45' : ''}`}
      >
        <span className={`mt-1.5 inline-block size-1.5 shrink-0 rounded-full ${style.dot}`} />
        <span className="w-16 shrink-0 font-mono text-[10px] text-scope-faint">
          {formatClock(entry.timestamp)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className={`font-mono text-xs ${failed ? 'text-signal-risk' : style.text}`}>
              {entry.event}
            </span>
            {actionOf(entry) && (
              <span className="font-mono text-[11px] text-scope-dim">{actionOf(entry)}</span>
            )}
            {folded && (
              <span
                className="chip border-signal-plan/40 text-signal-plan"
                title="构造上下文时跳过了这条，但原文仍在会话日志里"
              >
                已折叠
              </span>
            )}
          </span>
          <Preview entry={entry} />
        </span>
        <span className="shrink-0 font-mono text-[10px] text-scope-faint">
          {entry.id.split('-').pop()}
        </span>
      </button>
    </li>
  )
}

/** 一行摘要。挑该事件里最有信息量的那个字段，而不是无脑 JSON.stringify。 */
function Preview({ entry }: { entry: SessionEntry }) {
  const text = previewText(entry)
  if (!text) return null
  return (
    <span className="mt-0.5 block truncate font-mono text-[11px] text-scope-faint">{text}</span>
  )
}

function previewText(entry: SessionEntry): string {
  switch (entry.event) {
    case 'run_start':
      return stringField(entry, 'task')
    case 'run_end':
      return stringField(entry, 'final_answer') || stringField(entry, 'status')
    case 'step':
      return stringField(entry, 'observation') || stringField(entry, 'thought')
    case 'tool_call':
      return stringField(entry, 'observation')
    case 'replan':
      return stringField(entry, 'reason')
    case 'message': {
      const role = stringField(entry, 'role')
      const content = stringField(entry, 'content')
      const chars = entry.payload.content_chars
      return content ? `${role}: ${content}` : `${role}: ${String(chars ?? '')} 字（已脱敏）`
    }
    case 'compaction': {
      const before = entry.payload.estimated_tokens_before
      const after = entry.payload.estimated_tokens_after
      if (typeof before === 'number' && typeof after === 'number') {
        return `${before} → ${after} tokens（${stringField(entry, 'phase') || 'compaction'}）`
      }
      return stringField(entry, 'phase')
    }
    case 'llm_call': {
      const messages = entry.payload.message_count
      const chars = entry.payload.prompt_chars
      return `${String(messages ?? '?')} 条消息 / ${String(chars ?? '?')} 字提示`
    }
    case 'plan': {
      const steps = entry.payload.steps
      return Array.isArray(steps) ? `${steps.length} 步计划` : ''
    }
    case 'fork':
      return `分叉自 ${stringField(entry, 'source')}`
    default:
      return stringField(entry, 'error') || stringField(entry, 'observation')
  }
}
