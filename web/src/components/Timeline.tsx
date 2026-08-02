/**
 * 执行链时间轴：一次运行的全部条目，按步骤分组。
 *
 * 被折叠过的 message 条目画成**虚线节点 + 虚线边框 + 明写「已折叠」**——但仍在列。
 * 这是本项目和别家最不一样的地方：折叠只追加一条派生记录，原文一条不删，
 * 所以事后还能逐条核对。上一版只是把它调成 45% 透明度，等于把最独特的不变式
 * 表达成了「这条不重要」，正好说反了。
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

/** 事件归类 → 节点色 / 事件名文字色。语义色只在这里定义一次。 */
const KIND_STYLE: Record<EventKind, { dot: string; text: string }> = {
  lifecycle: { dot: 'bg-ink-4', text: 'text-ink-2' },
  plan: { dot: 'bg-indigo', text: 'text-indigo-ink' },
  llm: { dot: 'bg-line-strong', text: 'text-ink-3' },
  tool: { dot: 'bg-blue', text: 'text-ink' },
  step: { dot: 'bg-ink', text: 'text-ink' },
  message: { dot: 'bg-line-strong', text: 'text-ink-3' },
  compaction: { dot: 'bg-indigo', text: 'text-indigo-ink' },
  replan: { dot: 'bg-indigo', text: 'text-indigo-ink' },
  critic: { dot: 'bg-orange', text: 'text-orange-ink' },
  guard: { dot: 'bg-orange', text: 'text-orange-ink' },
  failure: { dot: 'bg-red', text: 'text-red-ink' },
  other: { dot: 'bg-ink-4', text: 'text-ink-2' },
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
    <ol>
      {groups.map((group, index) => (
        <li key={`${group.stepNumber ?? 'x'}-${index}`}>
          <div className="sticky top-0 z-10 flex items-center gap-2.5 border-y border-line bg-muted/85 px-5 py-2 backdrop-blur">
            <span className="text-micro font-semibold text-ink-2">
              {group.stepNumber === null ? '运行级' : `步骤 ${group.stepNumber}`}
            </span>
            {group.action && (
              <span
                className={`font-mono text-micro ${group.failed ? 'text-red-ink' : 'text-ink-2'}`}
              >
                {group.action}
              </span>
            )}
            {group.failed && (
              <span className="chip border-red/25 bg-red/10 text-red-ink">失败</span>
            )}
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
        data-entry-id={entry.id}
        onClick={() => onSelect(entry)}
        className={`focus-ring flex w-full gap-3 px-5 text-left transition-colors ${
          selected ? 'bg-blue/[0.07]' : 'hover:bg-muted/60'
        }`}
      >
        {/* 时间轴轨道：每行画一段竖线，行行相接即成连续的轴。 */}
        <span className="relative flex w-3 shrink-0 justify-center">
          <span className="absolute inset-y-0 w-px bg-line" aria-hidden="true" />
          <span
            className={`relative mt-3 size-2 shrink-0 rounded-full ring-2 ring-surface ${
              folded ? 'border border-dashed border-indigo bg-surface' : style.dot
            }`}
            aria-hidden="true"
          />
        </span>

        <span
          className={`min-w-0 flex-1 py-2.5 ${
            folded ? 'border-l-2 border-dashed border-indigo/35 pl-2.5' : ''
          }`}
        >
          <span className="flex flex-wrap items-center gap-2">
            <span className={`font-mono text-caption ${failed ? 'text-red-ink' : style.text}`}>
              {entry.event}
            </span>
            {actionOf(entry) && (
              <span className="font-mono text-micro text-ink-2">{actionOf(entry)}</span>
            )}
            {folded && (
              <span className="chip border-indigo/25 bg-indigo/10 text-indigo-ink">
                已折叠 · 原文仍在
              </span>
            )}
          </span>
          <Preview entry={entry} />
        </span>

        <span className="shrink-0 py-2.5 text-right">
          <span className="block font-mono text-micro tabular-nums text-ink-3">
            {formatClock(entry.timestamp)}
          </span>
          <span className="block font-mono text-micro tabular-nums text-ink-4">
            {entry.id.split('-').pop()}
          </span>
        </span>
      </button>
    </li>
  )
}

/** 一行摘要。挑该事件里最有信息量的那个字段，而不是无脑 JSON.stringify。 */
function Preview({ entry }: { entry: SessionEntry }) {
  const text = previewText(entry)
  if (!text) return null
  return <span className="mt-1 block truncate text-micro text-ink-3">{text}</span>
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
