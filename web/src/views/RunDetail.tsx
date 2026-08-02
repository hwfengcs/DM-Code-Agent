/**
 * 运行详情：控制台的主视图。
 *
 * 三栏——左边计划与元信息，中间三个审计分区（执行链 / 诊断 / 上下文折叠），
 * 右边选中条目的完整 payload。「从这里分叉」挂在右栏，因为分叉的语义就是
 * 「从当前选中这条重来」。
 *
 * 两处刻意的可审计设计：
 *   1. 验证缺口用**首屏横幅**而不是埋在诊断分区里——「成功但没验证」是这个项目
 *      最想让人看见的结论，藏在二级 tab 里等于没说。
 *   2. `parent_id` 可点击跳转。那根把 JSONL 串成树的指针应当是可导航的，
 *      而不是一行死文本。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, fetchAllEntries } from '../lib/api'
import type { SessionAnalysis, SessionEntry, SessionSummary } from '../lib/types'
import { foldedEntryIds, formatDuration, splitRuns } from '../lib/entries'
import { looksLikeConversation, splitTurns } from '../lib/turns'
import { hrefFor } from '../lib/router'
import {
  Banner,
  Button,
  ErrorBox,
  HealthBadge,
  JsonView,
  LinkButton,
  MetaRow,
  PageHeader,
  Panel,
  Segmented,
  Spinner,
  StatusChip,
} from '../components/ui'
import { Timeline } from '../components/Timeline'
import { ChatTurn } from '../components/ChatTurn'
import { Diagnostics } from '../components/Diagnostics'
import { CompactionView } from '../components/CompactionView'

type Tab = 'conversation' | 'timeline' | 'diagnostics' | 'compaction'

const TAB_TITLE: Record<Tab, string> = {
  conversation: '对话',
  timeline: '执行链',
  diagnostics: '诊断',
  compaction: '上下文折叠',
}

interface RunData {
  summary: SessionSummary
  analysis: SessionAnalysis
  entries: SessionEntry[]
}

export function RunDetail({
  session,
  readOnly,
  compareWith,
  onCompareWith,
  onSessionCreated,
}: {
  session: string
  readOnly: boolean
  compareWith: string | null
  onCompareWith: (name: string | null) => void
  onSessionCreated: () => void
}) {
  const [data, setData] = useState<RunData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('conversation')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [runIndex, setRunIndex] = useState(0)
  const [forkNotice, setForkNotice] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setData(null)
    setError(null)
    setSelectedId(null)
    setRunIndex(0)
    setTab('conversation')
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

  // 对话分区看的是**整份日志**，不受 run 段筛选影响——多段 run 在对话里正是多轮，
  // 只显示其中一段等于把对话拆散了。其余分区（执行链 / 折叠）仍按所选段看。
  const turns = useMemo(() => (data ? splitTurns(data.entries) : []), [data])
  const canReadAsConversation = useMemo(
    () => (data ? looksLikeConversation(data.entries) : false),
    [data],
  )
  const tabOptions = useMemo(() => {
    const options: { value: Tab; label: string }[] = []
    if (canReadAsConversation) options.push({ value: 'conversation', label: '对话' })
    options.push(
      { value: 'timeline', label: '执行链' },
      { value: 'diagnostics', label: '诊断' },
      { value: 'compaction', label: '上下文折叠' },
    )
    return options
  }, [canReadAsConversation])

  // 老 1.x trace / 只含 checkpoint 条目的文件读不成对话，退回执行链而不是显示空白。
  useEffect(() => {
    if (!canReadAsConversation && tab === 'conversation') setTab('timeline')
  }, [canReadAsConversation, tab])

  const folded = useMemo(() => foldedEntryIds(visibleEntries), [visibleEntries])
  const selected = useMemo(
    () => data?.entries.find((entry) => entry.id === selectedId) ?? null,
    [data, selectedId],
  )

  // j / k 在执行链上下移动，Esc 清除选中。审计工具该有的键盘操作。
  useEffect(() => {
    if (tab !== 'timeline') return
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return
      if (event.metaKey || event.ctrlKey || event.altKey) return

      if (event.key === 'Escape') {
        setSelectedId(null)
        return
      }
      if (event.key !== 'j' && event.key !== 'k') return
      if (visibleEntries.length === 0) return
      event.preventDefault()

      setSelectedId((current) => {
        // 未选中时 index = -1，于是 j 和 k 都落到第 0 条。
        const index = current ? visibleEntries.findIndex((entry) => entry.id === current) : -1
        const next =
          event.key === 'j'
            ? Math.min(index + 1, visibleEntries.length - 1)
            : Math.max(index - 1, 0)
        return visibleEntries[next]?.id ?? current
      })
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [tab, visibleEntries])

  // 键盘移动后把选中项滚进视野。
  useEffect(() => {
    if (!selectedId) return
    const node = document.querySelector(`[data-entry-id="${CSS.escape(selectedId)}"]`)
    node?.scrollIntoView({ block: 'nearest' })
  }, [selectedId])

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
          <a
            href={hrefFor({ name: 'list' })}
            className="text-caption font-medium text-blue hover:underline"
          >
            ← 回到会话库
          </a>
        }
      />
    )
  }
  if (!data) return <Spinner label={`读取 ${session}`} />

  const { summary, analysis } = data
  const isCompareBase = compareWith === session
  const parentInView =
    selected?.parent_id && data.entries.some((entry) => entry.id === selected.parent_id)

  return (
    <>
      <PageHeader
        title={summary.task || session}
        description={<span className="font-mono text-micro">{session}</span>}
        back={{ href: hrefFor({ name: 'list' }), label: '会话库' }}
        actions={
          <>
            <StatusChip status={summary.status} />
            <HealthBadge health={analysis.trace_health} />
            {compareWith && compareWith !== session ? (
              <a
                href={hrefFor({ name: 'diff', a: compareWith, b: session })}
                className="focus-ring rounded-control border border-transparent bg-blue px-3.5 py-1.5 text-caption font-medium text-white transition-colors hover:bg-blue-ink"
              >
                与基准 diff
              </a>
            ) : (
              <Button
                onClick={() => onCompareWith(isCompareBase ? null : session)}
                title="选为 diff 的基准，再打开另一个会话即可对比"
              >
                {isCompareBase ? '取消基准' : '设为基准'}
              </Button>
            )}
          </>
        }
      >
        <dl className="mt-4 flex flex-wrap gap-x-8 gap-y-2">
          <Metric label="步数" value={String(summary.step_count)} />
          <Metric label="工具调用" value={String(summary.tool_call_count)} />
          <Metric
            label="重规划"
            value={String(summary.replan_count)}
            tone={summary.replan_count > 0 ? 'indigo' : undefined}
          />
          <Metric label="耗时" value={formatDuration(summary.duration_seconds)} />
          <Metric label="模型" value={`${summary.provider ?? '—'} / ${summary.model ?? '—'}`} />
          <Metric label="schema" value={summary.schema_version ?? '—'} />
        </dl>
      </PageHeader>

      <div className="min-h-0 flex-1 overflow-hidden px-8 py-5">
        <div className="flex h-full min-h-0 flex-col gap-4">
          {/* 首屏审计横幅。这两条结论不该等人点进二级分区才看见。 */}
          {analysis.verification.gap && (
            <Banner
              tone="warn"
              title="宣布完成前没跑过任何验证"
              action={<LinkButton onClick={() => setTab('diagnostics')}>查看诊断</LinkButton>}
            >
              这次运行报告成功，但全程没有执行 run_tests / run_linter 一类的验证动作——
              结果可能是对的，但这次运行本身没有给出任何证据。
            </Banner>
          )}
          {!analysis.verification.gap && analysis.trace_health.grade === 'risky' && (
            <Banner
              tone="risk"
              title={`过程健康度为「有风险」（${analysis.trace_health.score.toFixed(2)}）`}
              action={<LinkButton onClick={() => setTab('diagnostics')}>查看扣分项</LinkButton>}
            >
              共 {analysis.trace_health.issues.length} 项扣分。
            </Banner>
          )}

          {runs.length > 1 && tab !== 'conversation' && (
            <div className="surface-raised flex flex-wrap items-center gap-3 rounded-card px-4 py-2.5">
              <span className="text-caption text-ink-2">
                这份日志含 {runs.length} 段 run
                {canReadAsConversation && '（在「对话」分区里它们就是多轮）'}
              </span>
              <Segmented
                value={String(runIndex)}
                options={runs.map((segment) => ({
                  value: String(segment.index),
                  // 多轮对话共用一个 run_id，用它当标签会全部重复；任务文本才分得清。
                  label: `#${segment.index + 1} ${segment.task.slice(0, 14) || segment.runId.slice(0, 8)}`,
                }))}
                onChange={(value) => setRunIndex(Number(value))}
              />
            </div>
          )}

          <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[16rem_minmax(0,1fr)_22rem]">
            <PlanPanel summary={summary} className="hidden lg:flex" />

            <Panel
              title={TAB_TITLE[tab]}
              subtitle={
                tab === 'conversation' && turns.length > 1 ? `${turns.length} 轮` : undefined
              }
              actions={<Segmented value={tab} options={tabOptions} onChange={setTab} />}
              bodyClassName="overflow-auto"
            >
              {tab === 'conversation' && (
                // 与实时对话界面**同一个** ChatTurn 组件：它们本来就是同一份条目流，
                // 共用渲染器才谈得上「实时看到的和事后审计到的一致」。
                <div className="space-y-8 px-5 py-5">
                  {turns.map((turn) => (
                    <ChatTurn
                      key={`${turn.index}-${turn.startedAt}`}
                      turn={turn}
                      selectedId={selectedId}
                      onSelect={(entry) => setSelectedId(entry.id)}
                      defaultOpen={false}
                    />
                  ))}
                </div>
              )}
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
              subtitle={
                selected
                  ? selected.event
                  : tab === 'conversation'
                    ? '展开某一轮的「执行过程」，点其中一条'
                    : '在执行链里选一条（或用 j / k 键）'
              }
              actions={
                selected && !readOnly ? (
                  <Button size="sm" onClick={doFork} title="从这条条目分叉出一份新会话">
                    从这里分叉
                  </Button>
                ) : null
              }
              className="hidden lg:flex"
              bodyClassName="overflow-auto"
            >
              {forkNotice && (
                <p className="border-b border-line bg-blue/[0.06] px-5 py-2.5 text-micro text-blue-ink">
                  {forkNotice}
                </p>
              )}
              {selected ? (
                <div className="px-5 py-4">
                  <MetaRow
                    label="parent"
                    value={
                      selected.parent_id ? (
                        parentInView ? (
                          <button
                            type="button"
                            onClick={() => setSelectedId(selected.parent_id)}
                            className="focus-ring rounded font-mono text-blue hover:underline"
                            title="跳到父条目——这根指针就是把会话串成树的那一根"
                          >
                            {selected.parent_id}
                          </button>
                        ) : (
                          <span title="父条目不在当前所选 run 段内">{selected.parent_id}</span>
                        )
                      ) : (
                        '（根）'
                      )
                    }
                  />
                  <MetaRow label="run id" value={selected.run_id} />
                  <MetaRow label="时间" value={selected.timestamp} />
                  <div className="mt-4 border-t border-line pt-4 font-mono text-micro">
                    <JsonView value={selected.payload} />
                  </div>
                </div>
              ) : (
                <div className="px-5 py-4">
                  <p className="text-caption text-ink-2">
                    选中一条后这里显示它的完整 payload。会话日志是 append-only 的，
                    你在这里看到的就是磁盘上的原文。
                  </p>
                  {summary.final_answer && (
                    <div className="mt-5 border-t border-line pt-4">
                      <div className="text-micro font-medium text-ink-3">最终回答</div>
                      <p className="mt-1.5 text-caption break-words whitespace-pre-wrap text-ink">
                        {summary.final_answer}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </Panel>
          </div>
        </div>
      </div>
    </>
  )
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone?: 'indigo'
}) {
  return (
    <div>
      <dt className="text-micro text-ink-3">{label}</dt>
      <dd
        className={`text-caption font-medium tabular-nums ${
          tone === 'indigo' ? 'text-indigo-ink' : 'text-ink'
        }`}
      >
        {value}
      </dd>
    </div>
  )
}

function PlanPanel({ summary, className = '' }: { summary: SessionSummary; className?: string }) {
  const executed = new Set(summary.steps.map((step) => step.action).filter(Boolean))
  return (
    <Panel
      title={`计划（${summary.plan_steps.length} 步）`}
      className={className}
      bodyClassName="overflow-auto"
    >
      {summary.plan_steps.length === 0 ? (
        <p className="px-5 py-4 text-caption text-ink-3">这次运行没有生成计划。</p>
      ) : (
        <ol className="divide-y divide-line">
          {summary.plan_steps.map((step, index) => {
            const ran = step.action ? executed.has(step.action) : false
            return (
              <li key={index} className="px-5 py-3">
                <div className="flex items-center gap-2.5">
                  <span
                    className={`inline-block size-1.5 shrink-0 rounded-full ${
                      ran ? 'bg-green' : 'border border-line-strong bg-surface'
                    }`}
                    title={ran ? '执行链里出现过这个动作' : '计划里有，但执行链里没出现'}
                  />
                  <span className="tabular-nums text-micro text-ink-4">
                    {step.step_number ?? index + 1}
                  </span>
                  <span className="truncate font-mono text-micro text-ink">{step.action ?? '—'}</span>
                </div>
                {step.reason && (
                  <p className="mt-1 pl-7 text-micro text-ink-3">{step.reason}</p>
                )}
              </li>
            )
          })}
        </ol>
      )}
    </Panel>
  )
}
