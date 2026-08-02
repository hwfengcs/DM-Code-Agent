/**
 * 会话库：全部运行的总览。
 *
 * 这个页面要一眼回答的问题不是「哪些跑成功了」，而是**「哪些跑成功了但过程不健康」**——
 * 所以状态和健康度是两列而不是合成一个「成功/失败」，且「成功但不健康」那张统计卡
 * 用大字号突出显示。健康度那一列直接把首条扣分项写出来，不需要悬停。
 *
 * 删除说明：删的是**会话文件**，移进 `sessions/.trash/`。这与「原始数据永不删除」
 * 那条项目宪法不冲突——宪法说的是会话**内**的条目（append-only、折叠只追加派生记录、
 * 原文一条不删）。清理整个文件是用户的权利，所以给了回收站而不是 unlink。
 */
import { useMemo, useState } from 'react'
import { api } from '../lib/api'
import type { SessionCard, SessionListResponse } from '../lib/types'
import { describeIssue, formatBytes, formatDuration, formatRelative } from '../lib/entries'
import { hrefFor } from '../lib/router'
import {
  Banner,
  Button,
  EmptyState,
  HealthBadge,
  PageHeader,
  Panel,
  Segmented,
  Stat,
  StatusChip,
} from '../components/ui'

type HealthFilter = 'all' | 'good' | 'warning' | 'risky'

const HEALTH_OPTIONS: { value: HealthFilter; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'good', label: '健康' },
  { value: 'warning', label: '需注意' },
  { value: 'risky', label: '有风险' },
]

export function SessionList({
  data,
  readOnly,
  compareWith,
  onCompareWith,
  onRefresh,
}: {
  data: SessionListResponse
  readOnly: boolean
  compareWith: string | null
  onCompareWith: (name: string | null) => void
  onRefresh: () => void
}) {
  const [keyword, setKeyword] = useState('')
  const [healthFilter, setHealthFilter] = useState<HealthFilter>('all')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [confirming, setConfirming] = useState<string[] | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)

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

  const toggle = (name: string) =>
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })

  const allVisibleSelected = visible.length > 0 && visible.every((card) => selected.has(card.name))

  const doDelete = async (names: string[]) => {
    setDeleting(true)
    setNotice(null)
    try {
      if (names.length === 1) {
        const result = await api.deleteSession(names[0] as string)
        setNotice(`已移入回收站：${result.trashed_as}`)
      } else {
        const result = await api.deleteSessions(names)
        setNotice(
          result.failed.length === 0
            ? `已把 ${result.deleted.length} 个会话移入回收站。`
            : `${result.deleted.length} 个已移入回收站，${result.failed.length} 个失败：` +
                result.failed.map((item) => `${item.name}（${item.error}）`).join('；'),
        )
      }
      setSelected(new Set())
      onRefresh()
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setDeleting(false)
      setConfirming(null)
    }
  }

  return (
    <>
      <PageHeader
        title="会话库"
        description="每一次运行的 append-only 会话日志。任务成功不代表过程健康，两者分列。"
        actions={<Button onClick={onRefresh}>刷新</Button>}
      />

      <div className="min-h-0 flex-1 overflow-auto px-8 py-6">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="会话总数" value={String(data.aggregate.total)} />
          <Stat label="任务成功" value={String(data.aggregate.by_status.success ?? 0)} />
          <Stat
            label="过程健康"
            value={String(data.aggregate.by_health.good ?? 0)}
            tone={data.aggregate.by_health.good ? 'good' : 'neutral'}
          />
          <Stat
            label="成功但不健康"
            value={String(successButUnhealthy)}
            tone={successButUnhealthy ? 'warn' : 'neutral'}
            hint="任务成功 ≠ 过程健康"
            emphasis
          />
        </div>

        {notice && (
          <div className="mt-4">
            <Banner
              tone="info"
              title="删除结果"
              action={
                <Button size="sm" variant="ghost" onClick={() => setNotice(null)}>
                  知道了
                </Button>
              }
            >
              {notice}
            </Banner>
          </div>
        )}

        {selected.size > 0 && !readOnly && (
          <div className="surface-raised mt-4 flex flex-wrap items-center gap-3 rounded-card px-4 py-2.5">
            <span className="text-caption text-ink">已选中 {selected.size} 个会话</span>
            <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
              取消选择
            </Button>
            <Button
              size="sm"
              variant="danger"
              disabled={deleting}
              onClick={() => setConfirming([...selected])}
            >
              删除选中
            </Button>
          </div>
        )}

        <div className="mt-6">
          <Panel
            title={`会话（${visible.length}/${data.sessions.length}）`}
            actions={
              <>
                <input
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                  placeholder="搜索任务或文件名"
                  className="field focus-ring w-56 py-1.5 text-caption"
                />
                <Segmented
                  value={healthFilter}
                  options={HEALTH_OPTIONS}
                  onChange={setHealthFilter}
                />
              </>
            }
            bodyClassName="overflow-x-auto"
          >
            {visible.length === 0 ? (
              <EmptyState
                title={data.sessions.length ? '没有匹配的会话' : 'sessions 目录还是空的'}
                hint={
                  data.sessions.length ? (
                    '换个关键词或把健康度筛选切回「全部」。'
                  ) : (
                    <>
                      去「对话」发一句话，或者用命令行：
                      <code className="mx-1 rounded bg-muted px-1.5 py-0.5 font-mono text-ink">
                        dm-agent "任务" --trace sessions/run.jsonl
                      </code>
                    </>
                  )
                }
              />
            ) : (
              <table className="w-full border-collapse text-left">
                <thead>
                  <tr className="divider-soft border-b">
                    {!readOnly && (
                      <Th className="w-10">
                        <input
                          type="checkbox"
                          aria-label="全选当前列表"
                          checked={allVisibleSelected}
                          onChange={() =>
                            setSelected(
                              allVisibleSelected
                                ? new Set()
                                : new Set(visible.map((card) => card.name)),
                            )
                          }
                          className="focus-ring size-3.5 cursor-pointer align-middle accent-blue"
                        />
                      </Th>
                    )}
                    <Th className="w-[32%]">任务</Th>
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
                      readOnly={readOnly}
                      selected={selected.has(card.name)}
                      onToggle={() => toggle(card.name)}
                      isCompareBase={compareWith === card.name}
                      onCompareWith={onCompareWith}
                      onDelete={() => setConfirming([card.name])}
                    />
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
        </div>

        {data.errors.length > 0 && (
          <div className="mt-4">
            <Panel title={`无法解析的文件（${data.errors.length}）`}>
              <ul className="space-y-1.5 px-5 py-4 text-caption text-ink-2">
                {data.errors.map((error) => (
                  <li key={error.name}>
                    <span className="font-mono text-red-ink">{error.name}</span>
                    <span className="mx-1.5 text-ink-4">—</span>
                    {error.error}
                  </li>
                ))}
              </ul>
            </Panel>
          </div>
        )}
      </div>

      {confirming && (
        <ConfirmDelete
          names={confirming}
          busy={deleting}
          onCancel={() => setConfirming(null)}
          onConfirm={() => void doDelete(confirming)}
        />
      )}
    </>
  )
}

/**
 * 删除确认。
 *
 * 文案明确写出「移入 sessions/.trash/」以及「可以从文件夹里拿回来」——对一个主打
 * 可审计的工具，让用户清楚证据去哪了比一句「确定删除吗？」重要得多。
 */
function ConfirmDelete({
  names,
  busy,
  onCancel,
  onConfirm,
}: {
  names: string[]
  busy: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/25 p-6"
      role="dialog"
      aria-modal="true"
      onClick={onCancel}
    >
      <div
        className="card w-full max-w-md p-6 shadow-pop"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="text-heading font-semibold text-ink">
          删除 {names.length} 个会话？
        </h2>
        <p className="mt-2 text-caption text-ink-2">
          文件会被移进{' '}
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-ink">
            sessions/.trash/
          </code>
          ，从列表里消失但不会被抹掉。误删了直接从那个文件夹里拿回来即可。
        </p>
        <ul className="mt-3 max-h-40 space-y-1 overflow-auto">
          {names.map((name) => (
            <li key={name} className="truncate font-mono text-micro text-ink-3">
              {name}
            </li>
          ))}
        </ul>
        <div className="mt-5 flex justify-end gap-2">
          <Button onClick={onCancel} disabled={busy}>
            取消
          </Button>
          <Button variant="danger" onClick={onConfirm} disabled={busy}>
            {busy ? '处理中…' : '移入回收站'}
          </Button>
        </div>
      </div>
    </div>
  )
}

function Row({
  card,
  readOnly,
  selected,
  onToggle,
  isCompareBase,
  onCompareWith,
  onDelete,
}: {
  card: SessionCard
  readOnly: boolean
  selected: boolean
  onToggle: () => void
  isCompareBase: boolean
  onCompareWith: (name: string | null) => void
  onDelete: () => void
}) {
  return (
    <tr
      className={`divider-soft row-interactive border-b last:border-0 ${
        selected ? 'bg-blue/[0.05]' : 'hover:bg-muted/50'
      }`}
    >
      {!readOnly && (
        <Td>
          <input
            type="checkbox"
            aria-label={`选择 ${card.name}`}
            checked={selected}
            onChange={onToggle}
            className="focus-ring size-3.5 cursor-pointer align-middle accent-blue"
          />
        </Td>
      )}
      <Td>
        <a href={hrefFor({ name: 'run', session: card.name })} className="group block">
          <div className="truncate text-body font-medium text-ink group-hover:text-blue">
            {card.task || <span className="font-normal text-ink-3">（无任务描述）</span>}
          </div>
          <div className="mt-0.5 truncate font-mono text-micro text-ink-3">
            {card.name}
            {card.run_count > 1 && (
              <span className="ml-2 text-indigo-ink">· {card.run_count} 轮对话</span>
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
        {/* 首条扣分项直接写出来——上一版这些结论藏在 title 属性里，必须悬停才看得见。 */}
        {card.health.issues.length > 0 && (
          <div className="mt-1 max-w-[13rem] truncate text-micro text-ink-3">
            {describeIssue(card.health.issues[0] as string)}
            {card.health.issues.length > 1 && ` 等 ${card.health.issues.length} 项`}
          </div>
        )}
      </Td>
      <Td className="text-right text-caption tabular-nums text-ink">{card.step_count}</Td>
      <Td className="text-right text-caption tabular-nums">
        {card.replan_count > 0 ? (
          <span className="font-medium text-indigo-ink">{card.replan_count}</span>
        ) : (
          <span className="text-ink-4">0</span>
        )}
      </Td>
      <Td className="text-right text-caption tabular-nums text-ink-2">
        {formatDuration(card.duration_seconds)}
      </Td>
      <Td className="text-micro text-ink-3">{formatRelative(card.modified)}</Td>
      <Td className="text-right">
        <div className="flex justify-end gap-2">
          {isCompareBase ? (
            <Button size="sm" variant="primary" onClick={() => onCompareWith(null)}>
              取消基准
            </Button>
          ) : (
            <Button size="sm" onClick={() => onCompareWith(card.name)} title="选为 diff 的基准">
              设为基准
            </Button>
          )}
          <a
            href={hrefFor({ name: 'run', session: card.name })}
            className="focus-ring rounded-control border border-line-strong bg-surface px-2.5 py-1 text-micro font-medium text-ink transition-colors hover:border-ink-4 hover:bg-muted"
          >
            打开
          </a>
          {!readOnly && (
            <Button size="sm" variant="danger" onClick={onDelete} title="移入 sessions/.trash/">
              删除
            </Button>
          )}
        </div>
      </Td>
    </tr>
  )
}

function Th({ children, className = '' }: { children?: React.ReactNode; className?: string }) {
  return (
    <th
      className={`sticky top-0 z-10 bg-surface px-5 py-3 text-micro font-medium text-ink-3 ${className}`}
    >
      {children}
    </th>
  )
}

function Td({ children, className = '' }: { children?: React.ReactNode; className?: string }) {
  return <td className={`px-5 py-3.5 align-middle ${className}`}>{children}</td>
}
