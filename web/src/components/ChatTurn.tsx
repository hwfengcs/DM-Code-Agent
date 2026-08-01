/**
 * 对话里的一轮：用户气泡 + agent 气泡（内含可折叠的执行过程）。
 *
 * 这个组件被**两处**复用：实时对话视图，和历史会话的「对话」分区。它们本来就是
 * 同一份 append-only 条目流，共用渲染器意味着「实时看到的」与「事后审计到的」
 * 不可能出现口径差异——这是本项目最核心的那条不变式，对话化不能把它牺牲掉。
 *
 * 「执行过程」默认收起：对话界面的主线是问和答，中间干了什么是**可展开的证据**，
 * 不是必须被读完的噪音。但正在跑的那一轮默认展开——那时候过程就是进度。
 */
import { useEffect, useRef, useState } from 'react'
import type { SessionEntry } from '../lib/types'
import { classifyEvent, formatClock, isFailureEntry } from '../lib/entries'
import {
  describeActivity,
  describeActivityEntry,
  labelActivityEntry,
  type ConversationTurnView,
} from '../lib/turns'
import { StatusChip } from './ui'

export function ChatTurn({
  turn,
  selectedId,
  onSelect,
  defaultOpen,
}: {
  turn: ConversationTurnView
  selectedId: string | null
  onSelect: (entry: SessionEntry) => void
  /** 不传时按「运行中的轮次展开」这条默认规则。 */
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen ?? turn.running)
  const wasRunning = useRef(turn.running)

  // 一轮跑完后自动收起——除非用户已经手动展开过（那时 defaultOpen 也不该覆盖）。
  useEffect(() => {
    if (wasRunning.current && !turn.running && defaultOpen === undefined) setOpen(false)
    wasRunning.current = turn.running
  }, [turn.running, defaultOpen])

  const summary = describeActivity(turn)

  return (
    <article className="space-y-3">
      <UserBubble text={turn.task} index={turn.index} at={turn.startedAt} />

      <div className="flex gap-3">
        <Avatar running={turn.running} failed={turn.failed} />
        <div className="min-w-0 flex-1 space-y-2">
          {turn.activity.length > 0 && (
            <div className="surface-raised overflow-hidden rounded-card">
              <button
                type="button"
                onClick={() => setOpen((value) => !value)}
                className="focus-ring flex w-full items-center gap-2 px-3.5 py-2 text-left transition-colors hover:bg-muted/60"
                aria-expanded={open}
              >
                <Chevron open={open} />
                <span className="text-micro font-medium text-ink-2">执行过程</span>
                {summary && <span className="text-micro text-ink-3">{summary}</span>}
                {turn.failed && (
                  <span className="chip border-orange/25 bg-orange/10 text-orange-ink">
                    过程中有失败
                  </span>
                )}
                {turn.running && <span className="ml-auto text-micro text-blue-ink">进行中…</span>}
              </button>
              {open && (
                <ol className="divider-soft border-t">
                  {turn.activity.map((entry) => (
                    <ActivityRow
                      key={entry.id}
                      entry={entry}
                      selected={entry.id === selectedId}
                      onSelect={onSelect}
                    />
                  ))}
                </ol>
              )}
            </div>
          )}

          {turn.running ? (
            <Thinking />
          ) : (
            <AnswerBubble
              text={turn.answer}
              status={turn.status}
              at={turn.finishedAt}
              onOpenEnd={() => {
                const end = turn.entries[turn.entries.length - 1]
                if (end) onSelect(end)
              }}
            />
          )}
        </div>
      </div>
    </article>
  )
}

function UserBubble({ text, index, at }: { text: string; index: number; at: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] min-w-0">
        <div className="mb-1 flex items-center justify-end gap-2 text-micro text-ink-4">
          <span>第 {index} 轮</span>
          <span className="tabular-nums">{formatClock(at)}</span>
        </div>
        <div className="rounded-card rounded-tr-sm bg-ink px-4 py-2.5 text-body break-words whitespace-pre-wrap text-white">
          {text}
        </div>
      </div>
    </div>
  )
}

function AnswerBubble({
  text,
  status,
  at,
  onOpenEnd,
}: {
  text: string
  status: string
  at: string
  onOpenEnd: () => void
}) {
  return (
    <div className="min-w-0">
      {text ? (
        <div className="text-body leading-relaxed break-words whitespace-pre-wrap text-ink">
          {text}
        </div>
      ) : (
        <p className="text-body text-ink-3">这一轮没有给出最终回答。</p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {status && status !== 'success' && <StatusChip status={status} />}
        <span className="tabular-nums text-micro text-ink-4">{formatClock(at)}</span>
        <button
          type="button"
          onClick={onOpenEnd}
          className="focus-ring rounded text-micro text-ink-3 transition-colors hover:text-blue"
          title="看这一轮 run_end 条目的完整 payload"
        >
          查看原始记录
        </button>
      </div>
    </div>
  )
}

function ActivityRow({
  entry,
  selected,
  onSelect,
}: {
  entry: SessionEntry
  selected: boolean
  onSelect: (entry: SessionEntry) => void
}) {
  const failed = isFailureEntry(entry)
  const kind = classifyEvent(entry)
  const detail = describeActivityEntry(entry)

  return (
    <li>
      <button
        type="button"
        data-entry-id={entry.id}
        onClick={() => onSelect(entry)}
        className={`focus-ring flex w-full items-baseline gap-2.5 px-3.5 py-2 text-left transition-colors ${
          selected ? 'bg-blue/[0.07]' : 'hover:bg-muted/60'
        }`}
      >
        <span
          className={`mt-1.5 inline-block size-1.5 shrink-0 rounded-full ${
            failed ? 'bg-red' : kind === 'compaction' || kind === 'replan' ? 'bg-indigo' : 'bg-blue'
          }`}
          aria-hidden="true"
        />
        <span
          className={`shrink-0 font-mono text-micro ${failed ? 'text-red-ink' : 'text-ink-2'}`}
        >
          {labelActivityEntry(entry)}
        </span>
        {detail && <span className="min-w-0 flex-1 truncate text-micro text-ink-3">{detail}</span>}
        <span className="ml-auto shrink-0 tabular-nums text-micro text-ink-4">
          {formatClock(entry.timestamp)}
        </span>
      </button>
    </li>
  )
}

function Avatar({ running, failed }: { running: boolean; failed: boolean }) {
  return (
    <span
      className={`mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full border text-micro font-semibold ${
        failed
          ? 'border-orange/30 bg-orange/10 text-orange-ink'
          : 'border-line bg-subtle text-ink-3'
      }`}
      aria-hidden="true"
    >
      {running ? <span className="size-2 animate-pulse rounded-full bg-blue" /> : 'A'}
    </span>
  )
}

function Thinking() {
  return (
    <div className="flex items-center gap-2 text-body text-ink-3">
      <span className="inline-block size-3.5 animate-spin rounded-full border-2 border-line-strong border-t-blue" />
      正在执行…
    </div>
  )
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 12 12"
      fill="none"
      aria-hidden="true"
      className={`shrink-0 text-ink-4 transition-transform ${open ? 'rotate-90' : ''}`}
    >
      <path
        d="M4.5 2.5 8 6l-3.5 3.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
