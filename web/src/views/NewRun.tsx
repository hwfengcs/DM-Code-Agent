/**
 * 新建运行 + 实时跟随。
 *
 * 表单字段完全由 ``/api/meta`` 的 capability 目录驱动——后端加一个开关，这里自动
 * 多一个控件，不需要改前端。护栏类（默认开）与行为类（默认关）分开摆，因为它们的
 * 语义完全不同：前者是你一般不该动的安全网，后者是研究者按需逐个打开做 ablation 的。
 *
 * 实时部分复用与历史审计**同一个** Timeline 组件：live run 和历史 trace 是同一份
 * append-only 条目流，没有第二套渲染器。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, api, subscribeToRun, type RunOptions } from '../lib/api'
import type { CapabilityInfo, MetaResponse, RunRecord, SessionEntry } from '../lib/types'
import { foldedEntryIds } from '../lib/entries'
import { hrefFor } from '../lib/router'
import { Banner, Button, ErrorBox, JsonView, PageHeader, Panel, StatusChip } from '../components/ui'
import { Timeline } from '../components/Timeline'

export function NewRun({ meta, onFinished }: { meta: MetaResponse; onFinished: () => void }) {
  const [task, setTask] = useState('')
  const [provider, setProvider] = useState(meta.providers[0]?.name ?? 'deepseek')
  const [model, setModel] = useState('')
  const [options, setOptions] = useState<RunOptions>({})
  const [advanced, setAdvanced] = useState(false)
  const [record, setRecord] = useState<RunRecord | null>(null)
  const [entries, setEntries] = useState<SessionEntry[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const unsubscribe = useRef<(() => void) | null>(null)

  // 组件卸载时一定要断开 SSE，否则 EventSource 会在后台一直重连。
  useEffect(() => () => unsubscribe.current?.(), [])

  const selectedProvider = meta.providers.find((item) => item.name === provider)
  const guardrails = meta.capabilities.filter((item) => item.category === 'guardrail')
  const behaviors = meta.capabilities.filter((item) => item.category === 'behavior')
  const tunings = meta.capabilities.filter((item) => item.category === 'tuning')

  const start = useCallback(async () => {
    setError(null)
    setNotice(null)
    setEntries([])
    setSelectedId(null)
    try {
      const created = await api.createRun({ task, provider, model, options })
      setRecord(created)
      unsubscribe.current?.()
      unsubscribe.current = subscribeToRun(created.run_id, (event) => {
        switch (event.kind) {
          case 'status':
            setRecord(event.record)
            break
          case 'entry':
            // 按 id 去重：断线重连时 Last-Event-ID 之前的条目可能被重发。
            setEntries((current) =>
              current.some((item) => item.id === event.entry.id)
                ? current
                : [...current, event.entry],
            )
            break
          case 'malformed':
            setNotice(`第 ${event.lineIndex} 行无法解析，已跳过。`)
            break
          case 'done':
            setRecord(event.record)
            onFinished()
            break
          case 'error':
            setNotice(event.message)
            break
        }
      })
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause))
    }
  }, [task, provider, model, options, onFinished])

  const cancel = useCallback(async () => {
    if (!record) return
    try {
      setRecord(await api.cancelRun(record.run_id))
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : String(cause))
    }
  }, [record])

  const folded = useMemo(() => foldedEntryIds(entries), [entries])
  const selected = entries.find((entry) => entry.id === selectedId) ?? null
  const isRunning = record?.status === 'running'

  if (meta.server.read_only) {
    return (
      <ErrorBox
        title="只读模式下不能发起运行"
        detail="去掉 --read-only 重启 dm-agent-web 即可。只读模式是给公开分享用的。"
      />
    )
  }

  return (
    <>
      <PageHeader
        title="新建运行"
        description={
          <>
            agent 会在 <code className="font-mono text-ink">{meta.server.workspace}</code>{' '}
            里真实读写文件，全过程写入会话日志。
          </>
        }
      />

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 overflow-hidden px-8 py-5 lg:grid-cols-[24rem_minmax(0,1fr)]">
        <Panel title="任务与开关" bodyClassName="overflow-auto">
          <div className="space-y-5 px-5 py-4">
            <div>
              <label className="mb-1.5 block text-caption font-medium text-ink" htmlFor="task">
                任务
              </label>
              <textarea
                id="task"
                value={task}
                onChange={(event) => setTask(event.target.value)}
                rows={5}
                disabled={isRunning}
                placeholder="用自然语言描述要做什么，例如：把 retry 边界的 off-by-one 修掉并跑测试验证"
                className="field focus-ring resize-y"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1.5 block text-caption font-medium text-ink" htmlFor="provider">
                  供应商
                </label>
                <select
                  id="provider"
                  value={provider}
                  onChange={(event) => setProvider(event.target.value)}
                  disabled={isRunning}
                  className="field focus-ring"
                >
                  {meta.providers.map((item) => (
                    <option key={item.name} value={item.name}>
                      {item.name}
                      {item.api_key_present ? '' : '（未配 key）'}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-caption font-medium text-ink" htmlFor="model">
                  模型
                </label>
                <input
                  id="model"
                  value={model}
                  onChange={(event) => setModel(event.target.value)}
                  disabled={isRunning}
                  placeholder={selectedProvider?.model ?? ''}
                  className="field focus-ring font-mono"
                />
              </div>
            </div>

            {selectedProvider && !selectedProvider.api_key_present && (
              <Banner tone="warn" title={`环境里没有 ${selectedProvider.env_key}`}>
                这次运行会直接失败。在 <code className="font-mono">.env</code> 里配置后重启服务。
              </Banner>
            )}

            <section>
              <h3 className="text-caption font-semibold text-ink">行为开关</h3>
              <p className="mt-0.5 mb-2 text-micro text-ink-3">
                研究性能力，默认全关，逐个打开做对照实验。
              </p>
              <div className="space-y-0.5">
                {behaviors.map((item) => (
                  <Toggle
                    key={item.key}
                    info={item}
                    value={Boolean(options[item.key] ?? item.default)}
                    disabled={isRunning}
                    onChange={(value) => setOptions((old) => ({ ...old, [item.key]: value }))}
                  />
                ))}
              </div>
            </section>

            <Button onClick={() => setAdvanced((value) => !value)}>
              {advanced ? '收起' : '展开'}护栏与数值参数（{guardrails.length + tunings.length}）
            </Button>

            {advanced && (
              <div className="space-y-5 rounded-card border border-line bg-subtle px-4 py-4">
                <section>
                  <h3 className="text-caption font-semibold text-ink">护栏</h3>
                  <p className="mt-0.5 mb-2 text-micro text-ink-3">默认全开，一般不用动。</p>
                  <div className="space-y-0.5">
                    {guardrails.map((item) =>
                      item.kind === 'bool' ? (
                        <Toggle
                          key={item.key}
                          info={item}
                          value={Boolean(options[item.key] ?? item.default)}
                          disabled={isRunning}
                          onChange={(value) => setOptions((old) => ({ ...old, [item.key]: value }))}
                        />
                      ) : (
                        <NumberField
                          key={item.key}
                          info={item}
                          value={options[item.key]}
                          disabled={isRunning}
                          onChange={(value) => setOptions((old) => ({ ...old, [item.key]: value }))}
                        />
                      ),
                    )}
                  </div>
                </section>
                <section>
                  <h3 className="text-caption font-semibold text-ink">数值参数</h3>
                  <div className="mt-2 space-y-0.5">
                    {tunings.map((item) => (
                      <NumberField
                        key={item.key}
                        info={item}
                        value={options[item.key]}
                        disabled={isRunning}
                        onChange={(value) => setOptions((old) => ({ ...old, [item.key]: value }))}
                      />
                    ))}
                  </div>
                </section>
              </div>
            )}

            <div className="flex items-center gap-2 border-t border-line pt-4">
              <Button
                variant="primary"
                onClick={() => void start()}
                disabled={isRunning || !task.trim()}
              >
                {isRunning ? '运行中…' : '开始运行'}
              </Button>
              {isRunning && (
                <Button variant="danger" onClick={() => void cancel()}>
                  停止
                </Button>
              )}
            </div>

            {error && <p className="text-caption text-red-ink">{error}</p>}
          </div>
        </Panel>

        <div className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)] gap-4">
          <div className="card px-5 py-3.5">
            {record ? (
              <div className="flex flex-wrap items-center gap-3">
                <StatusChip status={record.status} />
                {record.agent_status && record.agent_status !== 'success' && (
                  <span
                    className="chip border-orange/25 bg-orange/10 text-orange-ink"
                    title="agent 自己在 run_end 里报的状态。退出码 0 不代表它做完了。"
                  >
                    agent: {record.agent_status}
                  </span>
                )}
                <span className="font-mono text-micro text-ink-2">{record.run_id}</span>
                <a
                  href={hrefFor({ name: 'run', session: record.session })}
                  className="focus-ring rounded font-mono text-micro text-blue hover:underline"
                >
                  {record.session}
                </a>
                <span className="tabular-nums text-micro text-ink-3">{entries.length} 条条目</span>
                {record.exit_code !== null && (
                  <span className="tabular-nums text-micro text-ink-3">
                    退出码 {record.exit_code}
                  </span>
                )}
                {notice && <span className="text-micro text-orange-ink">{notice}</span>}
              </div>
            ) : (
              <p className="text-caption text-ink-3">
                还没有运行。左侧填好任务后点「开始运行」，这里会实时显示每一步。
              </p>
            )}
            {record?.error && (
              <pre className="mt-3 max-h-32 overflow-auto rounded-control bg-red/[0.06] p-3 font-mono text-micro break-words whitespace-pre-wrap text-red-ink">
                {record.error}
              </pre>
            )}
          </div>

          <div className="grid min-h-0 grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
            <Panel title="实时执行链" bodyClassName="overflow-auto">
              {entries.length === 0 ? (
                <p className="px-5 py-4 text-caption text-ink-3">
                  {isRunning ? '等待第一条条目…' : '条目会在运行开始后出现。'}
                </p>
              ) : (
                <Timeline
                  entries={entries}
                  foldedIds={folded}
                  selectedId={selectedId}
                  onSelect={(entry) => setSelectedId(entry.id)}
                />
              )}
            </Panel>
            <Panel
              title={selected ? `条目 ${selected.id}` : '条目详情'}
              subtitle={selected ? selected.event : undefined}
              className="hidden xl:flex"
              bodyClassName="overflow-auto"
            >
              {selected ? (
                <div className="px-5 py-4 font-mono text-micro">
                  <JsonView value={selected.payload} />
                </div>
              ) : (
                <p className="px-5 py-4 text-caption text-ink-3">
                  选一条条目看它的完整 payload。你看到的就是磁盘上会话日志里的原文。
                </p>
              )}
            </Panel>
          </div>
        </div>
      </div>
    </>
  )
}

function Toggle({
  info,
  value,
  disabled,
  onChange,
}: {
  info: CapabilityInfo
  value: boolean
  disabled: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <label
      className="flex cursor-pointer items-center gap-3 rounded-control px-2 py-2 transition-colors hover:bg-muted"
      title={info.help}
    >
      <span className="min-w-0 flex-1">
        <span className="block truncate text-caption text-ink">{info.label}</span>
        <span className="block truncate font-mono text-micro text-ink-4">{info.flag}</span>
      </span>
      <span className="relative inline-block shrink-0">
        <input
          type="checkbox"
          checked={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
          className="peer sr-only"
        />
        <span className="block h-5 w-9 rounded-full bg-line-strong transition-colors peer-checked:bg-green peer-disabled:opacity-40" />
        <span className="pointer-events-none absolute top-0.5 left-0.5 size-4 rounded-full bg-white shadow-sm transition-transform peer-checked:translate-x-4" />
      </span>
    </label>
  )
}

function NumberField({
  info,
  value,
  disabled,
  onChange,
}: {
  info: CapabilityInfo
  value: boolean | number | undefined
  disabled: boolean
  onChange: (value: number) => void
}) {
  const current = typeof value === 'number' ? value : Number(info.default)
  return (
    <label className="flex items-center gap-3 px-2 py-2" title={info.help}>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-caption text-ink">{info.label}</span>
        <span className="block truncate font-mono text-micro text-ink-4">{info.flag}</span>
      </span>
      <input
        type="number"
        value={current}
        step={info.kind === 'float' ? 0.1 : 1}
        disabled={disabled}
        onChange={(event) => onChange(Number(event.target.value))}
        className="field focus-ring w-24 shrink-0 px-2 py-1 text-caption tabular-nums"
      />
    </label>
  )
}
