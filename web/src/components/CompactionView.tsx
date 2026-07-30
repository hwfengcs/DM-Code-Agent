/**
 * 折叠视图——本项目最难用文字讲清、但一看就懂的那个特性。
 *
 * 别的 agent 压缩上下文 = 扇掉历史，事后没法追。这里折叠只**追加**一条 compaction
 * 派生记录，被折叠的原文一条都没删，只是构造下一次请求时跳过。所以这个页面能把
 * 「折叠了什么」和「原文长什么样」并排放在一起——右边那些暗着的条目就是证据。
 */
import { useState } from 'react'
import type { SessionEntry } from '../lib/types'
import { compactionSpans, formatClock, stringField } from '../lib/entries'
import { EmptyState, Panel } from './ui'

export function CompactionView({ entries }: { entries: SessionEntry[] }) {
  const spans = compactionSpans(entries)
  const byId = new Map(entries.map((entry) => [entry.id, entry]))

  if (spans.length === 0) {
    return (
      <EmptyState
        title="这次运行没有发生上下文折叠"
        hint="折叠按消息节奏或 token 预算触发；短会话通常不会触发。"
      />
    )
  }

  const totalSaved = spans.reduce((sum, span) => {
    if (span.tokensBefore === null || span.tokensAfter === null) return sum
    return sum + Math.max(0, span.tokensBefore - span.tokensAfter)
  }, 0)
  const totalFolded = spans.reduce((sum, span) => sum + span.foldedIds.length, 0)

  return (
    <div className="space-y-3 p-3">
      <div className="grid grid-cols-3 gap-3">
        <Stat label="折叠次数" value={String(spans.length)} />
        <Stat label="估算节省" value={`${totalSaved} tokens`} tone="good" />
        <Stat
          label="被删除的原文"
          value="0 条"
          tone="good"
          hint={`${totalFolded} 条被跳过，全部仍在日志里`}
        />
      </div>

      <p className="px-1 text-[11px] text-scope-faint">
        折叠是本地确定性的（不额外调 LLM），且带净收益护栏：只有
        <code className="mx-1 rounded bg-scope-raised px-1 font-mono">
          estimated_tokens_after &lt; estimated_tokens_before
        </code>
        才提交，压亏了整体回滚。下面每一条都能展开看被折叠的原文——它们仍在会话日志里。
      </p>

      {spans.map((span) => (
        <Panel
          key={span.entry.id}
          title={`compaction ${span.entry.id}`}
          subtitle={`${formatClock(span.entry.timestamp)} · ${span.phase || 'compaction'}${
            span.trigger ? ` · trigger=${span.trigger}` : ''
          }`}
        >
          <div className="space-y-2 p-3">
            <div className="flex items-center gap-3 font-mono text-xs">
              <span className="text-scope-dim">{span.tokensBefore ?? '?'}</span>
              <span className="text-signal-plan">→</span>
              <span className="text-signal-good">{span.tokensAfter ?? '?'}</span>
              <span className="text-scope-faint">tokens</span>
              {span.tokensBefore !== null && span.tokensAfter !== null && (
                <span
                  className={
                    span.tokensAfter < span.tokensBefore ? 'text-signal-good' : 'text-signal-warn'
                  }
                >
                  {span.tokensAfter < span.tokensBefore
                    ? `节省 ${span.tokensBefore - span.tokensAfter}`
                    : '无收益（应已回滚）'}
                </span>
              )}
              {span.phase === 'sticky_reuse' && (
                <span
                  className="chip border-signal-plan/40 text-signal-plan"
                  title="复用了上一次已证明正收益的折叠结果，不计为一次新压缩"
                >
                  粘性复用
                </span>
              )}
            </div>

            <div className="font-mono text-[11px] text-scope-faint">
              保留起点 first_kept_entry_id ={' '}
              <span className="text-scope-dim">{span.firstKeptId || '—'}</span>
            </div>

            <FoldedList ids={span.foldedIds} byId={byId} />
          </div>
        </Panel>
      ))}
    </div>
  )
}

function FoldedList({
  ids,
  byId,
}: {
  ids: string[]
  byId: Map<string, SessionEntry>
}) {
  const [open, setOpen] = useState(false)
  if (ids.length === 0) {
    return <p className="font-mono text-[11px] text-scope-faint">这条折叠没有记录具体条目 id。</p>
  }
  return (
    <div className="rounded border border-scope-line-soft">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="focus-ring flex w-full items-center justify-between px-2 py-1.5 text-left"
      >
        <span className="font-mono text-[11px] text-scope-dim">
          被跳过的 {ids.length} 条原文（仍在日志里）
        </span>
        <span className="font-mono text-[11px] text-signal-info">{open ? '收起' : '展开'}</span>
      </button>
      {open && (
        <ul className="divide-y divide-scope-line-soft/60 border-t border-scope-line-soft">
          {ids.map((id) => {
            const entry = byId.get(id)
            return (
              <li key={id} className="px-2 py-1.5 opacity-60">
                <div className="flex items-center gap-2 font-mono text-[10px] text-scope-faint">
                  <span>{id}</span>
                  {entry && <span>{stringField(entry, 'role') || entry.event}</span>}
                </div>
                <p className="mt-0.5 line-clamp-3 font-mono text-[11px] break-words whitespace-pre-wrap text-scope-dim">
                  {entry
                    ? stringField(entry, 'content') ||
                      `（保真档只留了长度与指纹：${String(entry.payload.content_chars ?? '?')} 字）`
                    : '（该条目不在当前所选前缀内）'}
                </p>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

function Stat({
  label,
  value,
  tone = 'neutral',
  hint,
}: {
  label: string
  value: string
  tone?: 'neutral' | 'good'
  hint?: string
}) {
  return (
    <div className="panel px-3 py-2">
      <div className="meta-label">{label}</div>
      <div className={`font-mono text-lg ${tone === 'good' ? 'text-signal-good' : 'text-scope-text'}`}>
        {value}
      </div>
      {hint && <div className="text-[11px] text-scope-faint">{hint}</div>}
    </div>
  )
}
