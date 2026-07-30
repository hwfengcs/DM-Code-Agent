/**
 * 运行详情：控制台的主视图。
 *
 * 三栏布局——左边计划与元信息，中间时间线（或诊断 / 折叠），右边选中条目的完整
 * payload。「从这里分叉」挂在右栏，因为分叉的语义就是「从当前选中这条重来」。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, fetchAllEntries } from '../lib/api'
import type { SessionAnalysis, SessionEntry, SessionSummary } from '../lib/types'
import { foldedEntryIds, formatDuration, splitRuns } from '../lib/entries'
import { hrefFor } from '../lib/router'
import { Button, ErrorBox, HealthBadge, JsonView, MetaRow, Panel, Spinner, StatusChip } from '../components/ui'
import { Timeline } from '../components/Timeline'
import { Diagnostics } from '../components/Diagnostics'
import { CompactionView } from '../components/CompactionView'

type Tab = 'timeline' | 'diagnostics' | 'compaction'

interface RunData {
  summary: SessionSummary
  analysis: SessionAnalysis
  entries: SessionEntry[]
}

export function RunDetail({
  session,
  readOnly,
  compareWith,
  onSessionCreated,
}: {
  session: string
  readOnly: boolean
  compareWith: string | null
  onSessionCreated: () => void
}) {
  const [data, setData] = useState<RunData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('timeline')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [runIndex, setRunIndex] = useState(0)
  const [forkNotice, setForkNotice] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setData(null)
    setError(null)
    setSelectedId(null)
    setRunIndex(0)
    Promise.all([api.summary(session), api.analysis(session), fetchAllEntries(session)])
      .then(([summary, analysis, entries]) => {
        if (cancelled) return
        setData({ summary: summary.summary, analysis: analysis.analysis, entries: entries.entries })
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : String(cause))
      })
    return () => {
      cancelled = true
    }
  }, [session])

  const runs = useMemo(() => (data ? splitRuns(data.entries) : []), [data])
  const visibleEntries = useMemo(() => {
    if (!data) return []
    const segment = runs[runIndex]
    if (!segment || runs.length <= 1) return data.entries
    return data.entries.slice(segment.startIndex, segment.endIndex + 1)
  }, [data, runs, runIndex])

  const folded = useMemo(() => foldedEntryIds(visibleEntries), [visibleEntries])
  const selected = useMemo(
    () => visibleEntries.find((entry) => entry.id === selectedId) ?? null,
    [visibleEntries, selectedId],
  )

  const doFork = useCallback(async () => {
    if (!selected) return
    try {
      const result = await api.fork(session, selected.id)
      setForkNotice(`已分叉到 ${result.output}（保留 ${result.entry_count} 条）`)
      onSessionCreated()
    } catch (cause) {
      setForkNotice(cause instanceof Error ? cause.message : String(cause))
    }
  }, [selected, session, onSessionCreated])

  if (error) {
    return (
      <ErrorBox
        title="打不开这个会话"
        detail={error}
        action={
          <a href={hrefFor({ name: 'list' })} className="font-mono text-xs text-signal-info hover:underline">
            ← 回到会话库
          </a>
        }
      />
    )
  }
  if (!data) return <Spinner label={`读取 ${session}`} />

  const { summary, analysis } = data

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-4">
      <header className="panel shrink-0 px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <a
                href={hrefFor({ name: 'list' })}
                className="font-mono text-xs text-scope-faint hover:text-signal-info"
              >
                ←
              </a>
              <h1 className="truncate text-sm text-scope-text">{summary.task || session}</h1>
            </div>
            <p className="mt-0.5 font-mono text-[11px] text-scope-faint">{session}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusChip status={summary.status} />
            <HealthBadge health={analysis.trace_health} />
            {compareWith && compareWith !== session && (
              <a
                href={hrefFor({ name: 'diff', a: compareWith, b: session })}
                className="focus-ring rounded border border-signal-info/50 bg-signal-info/10 px-2 py-1 font-mono text-[11px] text-signal-info"
              >
                与基准 diff
              </a>
            )}
          </div>
        </div>
        <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 font-mono text-[11px] text-scope-dim">
          <span>步数 {summary.step_count}</span>
          <span>工具 {summary.tool_call_count}</span>
          <span>重规划 {summary.replan_count}</span>
          <span>耗时 {formatDuration(summary.duration_seconds)}</span>
          <span>{summary.provider ?? '—'} / {summary.model ?? '—'}</span>
          <span>schema {summary.schema_version ?? '—'}</span>
        </div>
      </header>

      {runs.length > 1 && (
        <div className="panel flex shrink-0 flex-wrap items-center gap-2 px-3 py-2">
          <span className="meta-label">这份日志含 {runs.length} 段 run</span>
          {runs.map((segment) => (
            <Button
              key={segment.index}
              variant={segment.index === runIndex ? 'primary' : 'ghost'}
              onClick={() => setRunIndex(segment.index)}
            >
              #{segment.index + 1} {segment.runId.slice(0, 8)}
            </Button>
          ))}
        </div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-[minmax(0,15rem)_minmax(0,1fr)_minmax(0,22rem)]">
        <PlanPanel summary={summary} className="hidden lg:flex" />

        <Panel
          title="过程"
          actions={
            <>
              <Button variant={tab === 'timeline' ? 'primary' : 'ghost'} onClick={() => setTab('timeline')}>
                时间线
              </Button>
              <Button
                variant={tab === 'diagnostics' ? 'primary' : 'ghost'}
                onClick={() => setTab('diagnostics')}
              >
                诊断
              </Button>
              <Button
                variant={tab === 'compaction' ? 'primary' : 'ghost'}
                onClick={() => setTab('compaction')}
              >
                折叠
              </Button>
            </>
          }
          bodyClassName="overflow-auto"
        >
          {tab === 'timeline' && (
            <Timeline
              entries={visibleEntries}
              foldedIds={folded}
              selectedId={selectedId}
              onSelect={(entry) => setSelectedId(entry.id)}
            />
          )}
          {tab === 'diagnostics' && <Diagnostics analysis={analysis} />}
          {tab === 'compaction' && <CompactionView entries={visibleEntries} />}
        </Panel>

        <Panel
          title={selected ? `条目 ${selected.id}` : '条目详情'}
          subtitle={selected ? selected.event : '在左侧时间线里选一条'}
          actions={
            selected && !readOnly ? (
              <Button onClick={doFork} title="从这条条目分叉出一份新会话">
                从这里分叉
              </Button>
            ) : null
          }
          bodyClassName="overflow-auto"
        >
          {forkNotice && (
            <p className="border-b border-scope-line-soft px-3 py-2 font-mono text-[11px] text-signal-info">
              {forkNotice}
            </p>
          )}
          {selected ? (
            <div className="p-3">
              <MetaRow label="parent" value={selected.parent_id || '（根）'} />
              <MetaRow label="run id" value={selected.run_id} />
              <MetaRow label="时间" value={selected.timestamp} />
              <div className="mt-3 border-t border-scope-line-soft pt-3 font-mono text-xs">
                <JsonView value={selected.payload} />
              </div>
            </div>
          ) : (
            <div className="p-3">
              <p className="text-xs text-scope-faint">
                选中一条后这里显示它的完整 payload。会话日志是 append-only 的，
                你在这里看到的就是磁盘上的原文。
              </p>
              {summary.final_answer && (
                <div className="mt-4">
                  <div className="meta-label">最终回答</div>
                  <p className="mt-1 font-mono text-xs break-words whitespace-pre-wrap text-scope-text">
                    {summary.final_answer}
                  </p>
                </div>
              )}
            </div>
          )}
        </Panel>
      </div>
    </div>
  )
}

function PlanPanel({ summary, className = '' }: { summary: SessionSummary; className?: string }) {
  const executed = new Set(summary.steps.map((step) => step.action).filter(Boolean))
  return (
    <Panel title={`计划（${summary.plan_steps.length} 步）`} className={className} bodyClassName="overflow-auto">
      {summary.plan_steps.length === 0 ? (
        <p className="p-3 text-xs text-scope-faint">这次运行没有生成计划。</p>
      ) : (
        <ol className="divide-y divide-scope-line-soft/60">
          {summary.plan_steps.map((step, index) => {
            const ran = step.action ? executed.has(step.action) : false
            return (
              <li key={index} className="px-3 py-2">
                <div className="flex items-center gap-2">
                  <span
                    className={`inline-block size-1.5 rounded-full ${ran ? 'bg-signal-good' : 'bg-scope-line'}`}
                    title={ran ? '执行链里出现过这个动作' : '计划里有，但执行链里没出现'}
                  />
                  <span className="font-mono text-[11px] text-scope-faint">
                    {step.step_number ?? index + 1}
                  </span>
                  <span className="truncate font-mono text-xs text-scope-text">
                    {step.action ?? '—'}
                  </span>
                </div>
                {step.reason && (
                  <p className="mt-0.5 pl-6 text-[11px] text-scope-faint">{step.reason}</p>
                )}
              </li>
            )
          })}
        </ol>
      )}
    </Panel>
  )
}
