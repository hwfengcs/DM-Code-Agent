/**
 * 行为 diff：两次运行到底哪里不一样。
 *
 * 结论全部来自后端的 `diff_events`（与 `dm-agent-trace diff` 同一个函数）。
 * 前端只负责把动作序列对齐画出来——`common_prefix` 之前是一样的（弱化显示），
 * 从那之后开始分道扬镳（高亮）。
 */
import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { hrefFor } from '../lib/router'
import { ErrorBox, PageHeader, Panel, Spinner } from '../components/ui'

interface MetricDelta {
  base: number
  candidate: number
  delta: number
}

interface DiffPayload {
  base: Record<string, unknown>
  candidate: Record<string, unknown>
  status_changed: boolean
  task_changed: boolean
  final_answer_changed: boolean
  plan_changed: boolean
  metrics: Record<string, MetricDelta>
  action_sequence: {
    base: string[]
    candidate: string[]
    common_prefix: number
    changes: { index: number; base?: string; candidate?: string; kind?: string }[]
  }
  tool_usage: {
    base: Record<string, number>
    candidate: Record<string, number>
    delta: Record<string, MetricDelta>
  }
  plan: { base: string[]; candidate: string[] }
}

export function DiffView({ a, b }: { a: string; b: string }) {
  const [diff, setDiff] = useState<DiffPayload | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setDiff(null)
    setError(null)
    api
      .diff(a, b)
      .then((response) => {
        if (!cancelled) setDiff(response.diff as unknown as DiffPayload)
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : String(cause))
      })
    return () => {
      cancelled = true
    }
  }, [a, b])

  if (!a || !b) {
    return (
      <ErrorBox
        title="需要两个会话才能 diff"
        detail="在会话库里给一个会话「设为基准」，再打开另一个会话点「与基准 diff」。"
      />
    )
  }
  if (error) return <ErrorBox title="diff 失败" detail={error} />
  if (!diff) return <Spinner label="计算 diff" />

  const { action_sequence: actions } = diff
  const maxLength = Math.max(actions.base.length, actions.candidate.length)

  return (
    <>
      <PageHeader
        title="行为对比"
        description="两次运行的动作序列、指标与工具使用差异。结论由后端 diff_events 计算。"
        back={{ href: hrefFor({ name: 'list' }), label: '会话库' }}
      >
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <SessionRef label="基准" name={a} tone="base" />
          <SessionRef label="对比" name={b} tone="candidate" />
        </div>
      </PageHeader>

      <div className="min-h-0 flex-1 space-y-4 overflow-auto px-8 py-6">
        <div className="flex flex-wrap gap-2">
          <Flag label="状态" changed={diff.status_changed} />
          <Flag label="任务" changed={diff.task_changed} />
          <Flag label="计划" changed={diff.plan_changed} />
          <Flag label="最终回答" changed={diff.final_answer_changed} />
        </div>

        <Panel title="指标">
          <div className="grid grid-cols-2 gap-x-8 gap-y-4 px-5 py-4 sm:grid-cols-4">
            {Object.entries(diff.metrics).map(([key, value]) => (
              <div key={key}>
                <div className="text-micro text-ink-3">{key}</div>
                <div className="mt-0.5 flex items-baseline gap-1.5 tabular-nums">
                  <span className="text-caption text-ink-2">{format(value.base)}</span>
                  <span className="text-micro text-ink-4">→</span>
                  <span className="text-body font-medium text-ink">{format(value.candidate)}</span>
                  {value.delta !== 0 && (
                    <span
                      className={`text-micro font-medium ${
                        value.delta > 0 ? 'text-orange-ink' : 'text-green-ink'
                      }`}
                    >
                      {value.delta > 0 ? '+' : ''}
                      {format(value.delta)}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel
          title="动作序列"
          subtitle={`前 ${actions.common_prefix} 步完全一致，之后开始分叉`}
        >
          <div className="grid grid-cols-[3rem_1fr_1fr] gap-3 border-b border-line px-5 py-2 text-micro font-medium text-ink-3">
            <span>#</span>
            <span>基准</span>
            <span>对比</span>
          </div>
          <ol className="divide-y divide-line">
            {Array.from({ length: maxLength }, (_, index) => {
              const left = actions.base[index]
              const right = actions.candidate[index]
              const same = left === right
              const inCommonPrefix = index < actions.common_prefix
              return (
                <li
                  key={index}
                  className={`grid grid-cols-[3rem_1fr_1fr] gap-3 px-5 py-2 font-mono text-micro ${
                    inCommonPrefix ? 'text-ink-4' : ''
                  }`}
                >
                  <span className="tabular-nums text-ink-4">{index + 1}</span>
                  <span className={same ? 'text-ink-2' : 'font-medium text-orange-ink'}>
                    {left ?? '—'}
                  </span>
                  <span className={same ? 'text-ink-2' : 'font-medium text-blue-ink'}>
                    {right ?? '—'}
                  </span>
                </li>
              )
            })}
          </ol>
        </Panel>

        <Panel title="工具使用变化">
          <div className="px-5 py-4">
            {Object.keys(diff.tool_usage.delta).length === 0 ? (
              <p className="text-caption text-ink-3">两次运行用到的工具完全一致。</p>
            ) : (
              <ul className="space-y-2">
                {Object.entries(diff.tool_usage.delta).map(([tool, value]) => (
                  <li key={tool} className="flex items-baseline gap-4">
                    <span className="w-44 shrink-0 font-mono text-caption text-ink">{tool}</span>
                    <span className="tabular-nums text-caption text-ink-2">
                      {value.base} → {value.candidate}
                    </span>
                    <span
                      className={`text-micro font-medium tabular-nums ${
                        value.delta > 0 ? 'text-orange-ink' : 'text-green-ink'
                      }`}
                    >
                      {value.delta > 0 ? '+' : ''}
                      {value.delta}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Panel>
      </div>
    </>
  )
}

function SessionRef({
  label,
  name,
  tone,
}: {
  label: string
  name: string
  tone: 'base' | 'candidate'
}) {
  return (
    <div className="rounded-card border border-line bg-subtle px-4 py-3">
      <div className="flex items-center gap-2">
        <span
          className={`inline-block size-1.5 rounded-full ${
            tone === 'base' ? 'bg-orange' : 'bg-blue'
          }`}
        />
        <span className="text-micro font-medium text-ink-3">{label}</span>
      </div>
      <a
        href={hrefFor({ name: 'run', session: name })}
        className="focus-ring mt-1 block truncate rounded font-mono text-caption text-blue hover:underline"
      >
        {name}
      </a>
    </div>
  )
}

function Flag({ label, changed }: { label: string; changed: boolean }) {
  return (
    <span
      className={`chip ${
        changed
          ? 'border-orange/25 bg-orange/10 text-orange-ink'
          : 'border-line-strong bg-muted text-ink-3'
      }`}
    >
      {label} {changed ? '有变化' : '一致'}
    </span>
  )
}

function format(value: number | null): string {
  if (value === null || value === undefined) return '—'
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}
