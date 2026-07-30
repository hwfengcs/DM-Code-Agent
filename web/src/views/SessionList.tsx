/**
 * 会话库：全部运行的总览。
 *
 * 这个页面要一眼回答的问题不是「哪些跑成功了」，而是**「哪些跑成功了但过程不健康」**——
 * 所以状态和健康度是两列，而不是合成一个「成功/失败」。
 */
import { useMemo, useState } from 'react'
import type { SessionCard, SessionListResponse } from '../lib/types'
import { formatBytes, formatDuration, formatRelative } from '../lib/entries'
import { hrefFor } from '../lib/router'
import { Button, EmptyState, HealthBadge, Panel, StatusChip } from '../components/ui'

type HealthFilter = 'all' | 'good' | 'warning' | 'risky'

export function SessionList({
  data,
  compareWith,
  onCompareWith,
}: {
  data: SessionListResponse
  compareWith: string | null
  onCompareWith: (name: string | null) => void
}) {
  const [keyword, setKeyword] = useState('')
  const [healthFilter, setHealthFilter] = useState<HealthFilter>('all')

  const visible = useMemo(() => {
    const needle = keyword.trim().toLowerCase()
    return data.sessions.filter((card) => {
      if (healthFilter !== 'all' && card.health.grade !== healthFilter) return false
      if (!needle) return true
      return (
        card.name.toLowerCase().includes(needle) ||
        card.task.toLowerCase().includes(needle) ||
        card.status.toLowerCase().includes(needle)
      )
    })
  }, [data.sessions, keyword, healthFilter])

  // 「成功但不健康」的数量——这是本项目最想让人看见的一个数字。
  const successButUnhealthy = data.sessions.filter(
    (card) => card.status === 'success' && card.health.grade !== 'good',
  ).length

  return (
    <div className="mx-auto flex h-full w-full max-w-7xl flex-col gap-3 p-4">
      <div className="grid shrink-0 grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="会话总数" value={String(data.aggregate.total)} />
        <Stat label="成功" value={String(data.aggregate.by_status.success ?? 0)} />
        <Stat
          label="过程健康"
          value={String(data.aggregate.by_health.good ?? 0)}
          tone={data.aggregate.by_health.good ? 'good' : 'muted'}
        />
        <Stat
          label="成功但不健康"
          value={String(successButUnhealthy)}
          tone={successButUnhealthy ? 'warn' : 'muted'}
          hint="任务成功 ≠ 过程健康"
        />
      </div>

      <Panel
        title={`会话（${visible.length}/${data.sessions.length}）`}
        actions={
          <>
            <input
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder="搜索任务或文件名"
              className="focus-ring w-48 rounded border border-scope-line bg-scope-bg px-2 py-1 font-mono text-[11px] text-scope-text placeholder:text-scope-faint"
            />
            {(['all', 'good', 'warning', 'risky'] as const).map((grade) => (
              <Button
                key={grade}
                variant={healthFilter === grade ? 'primary' : 'ghost'}
                onClick={() => setHealthFilter(grade)}
              >
                {grade === 'all' ? '全部' : grade}
              </Button>
            ))}
          </>
        }
        className="min-h-0 flex-1"
        bodyClassName="overflow-auto"
      >
        {visible.length === 0 ? (
          <EmptyState
            title={data.sessions.length ? '没有匹配的会话' : 'sessions 目录还是空的'}
            hint={
              data.sessions.length ? (
                '换个关键词或把健康度筛选切回「全部」。'
              ) : (
                <>
                  跑一个任务并留下会话日志：
                  <code className="mx-1 rounded bg-scope-raised px-1 font-mono">
                    dm-agent "任务" --trace sessions/run.jsonl
                  </code>
                </>
              )
            }
          />
        ) : (
          <table className="w-full border-collapse text-left">
            <thead className="sticky top-0 z-10 bg-scope-panel">
              <tr className="border-b border-scope-line-soft">
                <Th className="w-[38%]">任务</Th>
                <Th>状态</Th>
                <Th>过程健康</Th>
                <Th className="text-right">步数</Th>
                <Th className="text-right">重规划</Th>
                <Th className="text-right">耗时</Th>
                <Th>更新</Th>
                <Th className="text-right">操作</Th>
              </tr>
            </thead>
            <tbody>
              {visible.map((card) => (
                <Row
                  key={card.name}
                  card={card}
                  isCompareBase={compareWith === card.name}
                  onCompareWith={onCompareWith}
                />
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      {data.errors.length > 0 && (
        <Panel title={`无法解析的文件（${data.errors.length}）`} className="shrink-0">
          <ul className="space-y-1 p-3 font-mono text-[11px] text-scope-dim">
            {data.errors.map((error) => (
              <li key={error.name}>
                <span className="text-signal-risk">{error.name}</span> — {error.error}
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  )
}

function Row({
  card,
  isCompareBase,
  onCompareWith,
}: {
  card: SessionCard
  isCompareBase: boolean
  onCompareWith: (name: string | null) => void
}) {
  return (
    <tr className="border-b border-scope-line-soft/60 transition-colors hover:bg-scope-raised/50">
      <Td>
        <a href={hrefFor({ name: 'run', session: card.name })} className="group block">
          <div className="truncate text-sm text-scope-text group-hover:text-signal-info">
            {card.task || <span className="text-scope-faint">（无任务描述）</span>}
          </div>
          <div className="truncate font-mono text-[11px] text-scope-faint">
            {card.name}
            {card.run_count > 1 && (
              <span className="ml-2 text-signal-warn">· 含 {card.run_count} 段 run</span>
            )}
            <span className="ml-2">· {formatBytes(card.size_bytes)}</span>
          </div>
        </a>
      </Td>
      <Td>
        <StatusChip status={card.status} />
      </Td>
      <Td>
        <HealthBadge health={card.health} />
      </Td>
      <Td className="text-right font-mono text-xs">{card.step_count}</Td>
      <Td className="text-right font-mono text-xs">
        {card.replan_count > 0 ? (
          <span className="text-signal-plan">{card.replan_count}</span>
        ) : (
          <span className="text-scope-faint">0</span>
        )}
      </Td>
      <Td className="text-right font-mono text-xs text-scope-dim">
        {formatDuration(card.duration_seconds)}
      </Td>
      <Td className="font-mono text-[11px] text-scope-faint">{formatRelative(card.modified)}</Td>
      <Td className="text-right">
        <div className="flex justify-end gap-1">
          {isCompareBase ? (
            <Button variant="primary" onClick={() => onCompareWith(null)}>
              取消对比基准
            </Button>
          ) : (
            <Button onClick={() => onCompareWith(card.name)} title="选为 diff 的基准">
              设为基准
            </Button>
          )}
          <a
            href={hrefFor({ name: 'run', session: card.name })}
            className="focus-ring rounded border border-scope-line bg-scope-raised px-2 py-1 font-mono text-[11px] text-scope-dim hover:text-scope-text"
          >
            打开
          </a>
        </div>
      </Td>
    </tr>
  )
}

function Stat({
  label,
  value,
  tone = 'muted',
  hint,
}: {
  label: string
  value: string
  tone?: 'muted' | 'good' | 'warn'
  hint?: string
}) {
  const color =
    tone === 'good' ? 'text-signal-good' : tone === 'warn' ? 'text-signal-warn' : 'text-scope-text'
  return (
    <div className="panel px-3 py-2">
      <div className="meta-label">{label}</div>
      <div className={`font-mono text-2xl ${color}`}>{value}</div>
      {hint && <div className="text-[11px] text-scope-faint">{hint}</div>}
    </div>
  )
}

function Th({ children, className = '' }: { children?: React.ReactNode; className?: string }) {
  return <th className={`meta-label px-3 py-2 font-normal ${className}`}>{children}</th>
}

function Td({ children, className = '' }: { children?: React.ReactNode; className?: string }) {
  return <td className={`px-3 py-2 align-middle ${className}`}>{children}</td>
}
