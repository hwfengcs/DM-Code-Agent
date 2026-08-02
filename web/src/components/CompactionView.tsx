/**
 * 上下文折叠视图——本项目最难用文字讲清、但一看就懂的那个特性。
 *
 * 别的 agent 压缩上下文 = 扇掉历史，事后没法追。这里折叠只**追加**一条 compaction
 * 派生记录，被折叠的原文一条都没删，只是构造下一次请求时跳过。所以这个页面能把
 * 「折叠了什么」和「原文长什么样」并排放在一起——展开那些条目就是证据。
 */
import { useState } from 'react'
import type { SessionEntry } from '../lib/types'
import { compactionSpans, formatClock, stringField } from '../lib/entries'
import { EmptyState, Stat } from './ui'

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
    <div className="space-y-4 p-5">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Stat label="折叠次数" value={String(spans.length)} />
        <Stat label="估算节省" value={`${totalSaved}`} hint="tokens" tone="good" />
        <Stat
          label="被删除的原文"
          value="0 条"
          tone="good"
          hint={`${totalFolded} 条被跳过，全部仍在日志里`}
        />
      </div>

      <p className="rounded-card border border-line bg-subtle px-4 py-3 text-micro text-ink-2">
        折叠是本地确定性的（不额外调 LLM），且带净收益护栏：只有
        <code className="mx-1 rounded bg-muted px-1.5 py-0.5 font-mono text-ink">
          estimated_tokens_after &lt; estimated_tokens_before
        </code>
        才提交，压亏了整体回滚。下面每一条都能展开看被折叠的原文——它们仍在会话日志里。
      </p>

      {spans.map((span) => (
        <section key={span.entry.id} className="card">
          <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3.5">
            <div className="min-w-0">
              <div className="font-mono text-caption text-ink">{span.entry.id}</div>
              <div className="mt-0.5 text-micro text-ink-3">
                {formatClock(span.entry.timestamp)} · {span.phase || 'compaction'}
                {span.trigger ? ` · trigger=${span.trigger}` : ''}
              </div>
            </div>
            {span.phase === 'sticky_reuse' && (
              <span
                className="chip border-indigo/25 bg-indigo/10 text-indigo-ink"
                title="复用了上一次已证明正收益的折叠结果，不计为一次新压缩"
              >
                粘性复用
              </span>
            )}
          </header>

          <div className="space-y-3 px-5 py-4">
            <div className="flex flex-wrap items-center gap-2.5 font-mono text-caption tabular-nums">
              <span className="text-ink-2">{span.tokensBefore ?? '?'}</span>
              <span className="text-indigo">→</span>
              <span className="font-medium text-ink">{span.tokensAfter ?? '?'}</span>
              <span className="text-micro text-ink-3">tokens</span>
              {span.tokensBefore !== null && span.tokensAfter !== null && (
                <span
                  className={`chip ${
                    span.tokensAfter < span.tokensBefore
                      ? 'border-green/25 bg-green/10 text-green-ink'
                      : 'border-orange/25 bg-orange/10 text-orange-ink'
                  }`}
                >
                  {span.tokensAfter < span.tokensBefore
                    ? `节省 ${span.tokensBefore - span.tokensAfter}`
                    : '无收益（应已回滚）'}
                </span>
              )}
            </div>

            <div className="text-micro text-ink-3">
              保留起点 <span className="font-mono">first_kept_entry_id</span> ={' '}
              <span className="font-mono text-ink-2">{span.firstKeptId || '—'}</span>
            </div>

            <FoldedList ids={span.foldedIds} byId={byId} />
          </div>
        </section>
      ))}
    </div>
  )
}

function FoldedList({ ids, byId }: { ids: string[]; byId: Map<string, SessionEntry> }) {
  const [open, setOpen] = useState(false)
  if (ids.length === 0) {
    return <p className="text-micro text-ink-3">这条折叠没有记录具体条目 id。</p>
  }
  return (
    <div className="overflow-hidden rounded-control border border-line">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="focus-ring flex w-full items-center justify-between gap-3 bg-subtle px-4 py-2.5 text-left transition-colors hover:bg-muted"
      >
        <span className="text-caption text-ink-2">
          被跳过的 <span className="font-medium text-ink">{ids.length}</span> 条原文（仍在日志里）
        </span>
        <span className="text-micro font-medium text-blue">{open ? '收起' : '展开核对'}</span>
      </button>
      {open && (
        <ul className="divide-y divide-line border-t border-line">
          {ids.map((id) => {
            const entry = byId.get(id)
            return (
              <li key={id} className="border-l-2 border-dashed border-indigo/35 px-4 py-2.5">
                <div className="flex items-center gap-2.5 font-mono text-micro text-ink-3">
                  <span>{id}</span>
                  {entry && <span className="text-ink-4">{stringField(entry, 'role') || entry.event}</span>}
                </div>
                <p className="mt-1 line-clamp-3 font-mono text-micro break-words whitespace-pre-wrap text-ink-2">
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
