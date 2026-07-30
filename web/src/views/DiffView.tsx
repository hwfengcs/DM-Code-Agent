/**
 * 行为 diff：两次运行到底哪里不一样。
 *
 * 结论全部来自后端的 `diff_events`（与 `dm-agent-trace diff` 同一个函数）。
 * 前端只负责把动作序列对齐画出来——`common_prefix` 之前是一样的，从那之后开始分道扬镳。
 */
import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { hrefFor } from '../lib/router'
import { ErrorBox, Panel, Spinner } from '../components/ui'

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
    <div className="mx-auto flex h-full w-full max-w-6xl flex-col gap-3 overflow-auto p-4">
      <header className="panel px-4 py-3">
        <div className="flex items-center gap-2">
          <a href={hrefFor({ name: 'list' })} className="font-mono text-xs text-scope-faint hover:text-signal-info">
            ←
          </a>
          <h1 className="meta-label">行为 diff</h1>
        </div>
        <div className="mt-2 grid grid-cols-2 gap-4 font-mono text-xs">
          <div>
            <div className="meta-label">基准</div>
            <a href={hrefFor({ name: 'run', session: a })} className="text-signal-info hover:underline">
              {a}
            </a>
          </div>
          <div>
            <div className="meta-label">对比</div>
            <a href={hrefFor({ name: 'run', session: b })} className="text-signal-info hover:underline">
              {b}
            </a>
          </div>
        </div>
      </header>

      <div className="flex flex-wrap gap-2">
        <Flag label="状态" changed={diff.status_changed} />
        <Flag label="任务" changed={diff.task_changed} />
        <Flag label="计划" changed={diff.plan_changed} />
        <Flag label="最终回答" changed={diff.final_answer_changed} />
      </div>

      <Panel title="指标">
        <div className="grid grid-cols-2 gap-x-6 p-3 sm:grid-cols-4">
          {Object.entries(diff.metrics).map(([key, value]) => (
            <div key={key}>
              <div className="meta-label">{key}</div>
              <div className="font-mono text-sm">
                <span className="text-scope-dim">{format(value.base)}</span>
                <span className="mx-1 text-scope-faint">→</span>
                <span className="text-scope-text">{format(value.candidate)}</span>
                {value.delta !== 0 && (
                  <span className={value.delta > 0 ? 'ml-2 text-signal-warn' : 'ml-2 text-signal-good'}>
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
        <ol className="divide-y divide-scope-line-soft/60">
          {Array.from({ length: maxLength }, (_, index) => {
            const left = actions.base[index]
            const right = actions.candidate[index]
            const same = left === right
            const inCommonPrefix = index < actions.common_prefix
            return (
              <li
                key={index}
                className={`grid grid-cols-[3rem_1fr_1fr] gap-2 px-3 py-1 font-mono text-xs ${
                  inCommonPrefix ? 'opacity-45' : ''
                }`}
              >
                <span className="text-scope-faint">{index + 1}</span>
                <span className={same ? 'text-scope-dim' : 'text-signal-warn'}>{left ?? '—'}</span>
                <span className={same ? 'text-scope-dim' : 'text-signal-info'}>{right ?? '—'}</span>
              </li>
            )
          })}
        </ol>
      </Panel>

      <Panel title="工具使用变化">
        <div className="p-3">
          {Object.keys(diff.tool_usage.delta).length === 0 ? (
            <p className="font-mono text-xs text-scope-faint">两次运行用到的工具完全一致。</p>
          ) : (
            <ul className="space-y-1">
              {Object.entries(diff.tool_usage.delta).map(([tool, value]) => (
                <li key={tool} className="flex items-baseline gap-3 font-mono text-xs">
                  <span className="w-40 shrink-0 text-scope-dim">{tool}</span>
                  <span className="text-scope-faint">
                    {value.base} → {value.candidate}
                  </span>
                  <span className={value.delta > 0 ? 'text-signal-warn' : 'text-signal-good'}>
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
  )
}

function Flag({ label, changed }: { label: string; changed: boolean }) {
  return (
    <span
      className={`chip ${
        changed
          ? 'border-signal-warn/40 bg-signal-warn/10 text-signal-warn'
          : 'border-scope-line bg-scope-raised text-scope-faint'
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
