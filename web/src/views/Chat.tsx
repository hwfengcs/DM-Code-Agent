/**
 * 对话主界面。
 *
 * 三条决定了它长什么样的判断：
 *
 * 1. **消息流由条目流推导，不另存一份状态**（见 `lib/turns.ts`）。所以实时看到的
 *    与事后在会话库里审计到的必然一致，历史会话也能用同一个渲染器打开。
 * 2. **对话化不牺牲可审计性**。右侧审计抽屉随时能看选中条目的完整 payload——
 *    这是本项目的立身之本，不能因为界面变好看了就藏起来。
 * 3. **设置在对话开始后锁定**。开关是 spawn 子进程时固化进 argv 的，跑起来之后
 *    再让用户去调只会撒谎。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { RunOptions } from '../lib/api'
import {
  endConversation,
  sendTurn,
  startConversation,
  useConversation,
} from '../lib/conversationStore'
import type { CapabilityInfo, MetaResponse, SessionEntry } from '../lib/types'
import { splitTurns } from '../lib/turns'
import { workspaceName } from '../lib/paths'
import { hrefFor } from '../lib/router'
import { Banner, Button, ErrorBox, JsonView, StatusChip } from '../components/ui'
import { ChatTurn } from '../components/ChatTurn'

export function Chat({ meta, onSessionsChanged }: { meta: MetaResponse; onSessionsChanged: () => void }) {
  const state = useConversation()
  const [draft, setDraft] = useState('')
  const [provider, setProvider] = useState(meta.providers[0]?.name ?? 'deepseek')
  const [model, setModel] = useState('')
  const [options, setOptions] = useState<RunOptions>({})
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const scroller = useRef<HTMLDivElement>(null)
  const finishedTurns = useRef(0)

  const turns = useMemo(() => splitTurns(state.entries), [state.entries])
  const record = state.record
  const busy = record?.busy ?? false
  const live = record?.status === 'idle' || record?.status === 'running'
  const selected = state.entries.find((entry) => entry.id === selectedId) ?? null

  // 新条目进来就贴底。用户往上翻看历史时不打扰他。
  useEffect(() => {
    const node = scroller.current
    if (!node) return
    const nearBottom = node.scrollHeight - node.scrollTop - node.clientHeight < 160
    if (nearBottom) node.scrollTo({ top: node.scrollHeight })
  }, [state.entries.length])

  // 每跑完一轮就刷新会话库——这次对话的日志刚刚多了一段 run。
  useEffect(() => {
    const done = record?.completed_turns ?? 0
    if (done > finishedTurns.current) {
      finishedTurns.current = done
      onSessionsChanged()
    }
  }, [record?.completed_turns, onSessionsChanged])

  const submit = useCallback(async () => {
    const task = draft.trim()
    if (!task || busy || state.pending) return
    if (!live) {
      const ok = await startConversation({ provider, model, options })
      if (!ok) return
    }
    if (await sendTurn(task)) setDraft('')
  }, [draft, busy, state.pending, live, provider, model, options])

  if (meta.server.read_only) {
    return (
      <ErrorBox
        title="只读模式下不能发起对话"
        detail="去掉 --read-only 重启 dm-agent-web 即可。只读模式是给公开分享用的，它仍然能审计全部历史会话。"
      />
    )
  }

  const selectedProvider = meta.providers.find((item) => item.name === provider)

  return (
    <div className="flex h-full min-h-0">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <ChatHeader
          meta={meta}
          record={record}
          onEnd={() => void endConversation()}
          onToggleInspector={() => setInspectorOpen((value) => !value)}
          inspectorOpen={inspectorOpen}
        />

        <div ref={scroller} className="min-h-0 flex-1 overflow-auto">
          <div className="mx-auto w-full max-w-[46rem] space-y-8 px-6 py-8">
            {state.notice && (
              <Banner tone="warn" title="提示">
                {state.notice}
              </Banner>
            )}
            {record?.error && (
              <Banner tone="risk" title="agent 进程报错">
                <pre className="mt-1 max-h-40 overflow-auto font-mono text-micro break-words whitespace-pre-wrap">
                  {record.error}
                </pre>
              </Banner>
            )}

            {turns.length === 0 ? (
              <EmptyChat
                workspace={workspaceName(meta)}
                restoring={state.restoring}
                onPick={setDraft}
              />
            ) : (
              turns.map((turn) => (
                <ChatTurn
                  key={`${turn.index}-${turn.startedAt}`}
                  turn={turn}
                  selectedId={selectedId}
                  onSelect={(entry) => {
                    setSelectedId(entry.id)
                    setInspectorOpen(true)
                  }}
                />
              ))
            )}

            {/* 已提交但 run_start 还没落盘的那一小段空窗，不能让界面看起来没反应。 */}
            {busy && turns.length < (record?.submitted_turns ?? 0) && (
              <p className="text-body text-ink-3">正在启动这一轮…</p>
            )}
          </div>
        </div>

        <Composer
          draft={draft}
          onDraft={setDraft}
          onSubmit={() => void submit()}
          disabled={busy || state.pending}
          busy={busy}
          live={live}
          workspace={workspaceName(meta)}
          error={state.error}
          settings={
            <SettingsBar
              meta={meta}
              locked={live}
              open={settingsOpen}
              onToggle={() => setSettingsOpen((value) => !value)}
              provider={provider}
              onProvider={setProvider}
              model={model}
              onModel={setModel}
              options={options}
              onOptions={setOptions}
              missingKey={selectedProvider && !selectedProvider.api_key_present ? selectedProvider.env_key : ''}
            />
          }
        />
      </div>

      {inspectorOpen && (
        <Inspector entry={selected} onClose={() => setInspectorOpen(false)} />
      )}
    </div>
  )
}

function ChatHeader({
  meta,
  record,
  onEnd,
  onToggleInspector,
  inspectorOpen,
}: {
  meta: MetaResponse
  record: ReturnType<typeof useConversation>['record']
  onEnd: () => void
  onToggleInspector: () => void
  inspectorOpen: boolean
}) {
  const live = record?.status === 'idle' || record?.status === 'running'
  return (
    <header className="divider-soft flex shrink-0 flex-wrap items-center gap-3 border-b bg-canvas px-6 py-3.5">
      <h1 className="text-heading font-semibold text-ink">对话</h1>
      {record ? (
        <>
          <StatusChip status={record.status} />
          <span className="tabular-nums text-micro text-ink-3">
            {record.completed_turns}/{record.submitted_turns} 轮
          </span>
          <a
            href={hrefFor({ name: 'run', session: record.session })}
            className="focus-ring rounded font-mono text-micro text-blue hover:underline"
            title="在会话库里以审计视图打开这次对话的日志"
          >
            {record.session}
          </a>
        </>
      ) : (
        <span className="text-micro text-ink-3">
          在 <span className="font-mono text-ink-2">{workspaceName(meta)}</span> 里干活，全程写入会话日志
        </span>
      )}
      <div className="ml-auto flex items-center gap-2">
        <Button size="sm" onClick={onToggleInspector} title="选中执行过程里的某条记录后，这里显示它的完整 payload">
          {inspectorOpen ? '收起审计面板' : '审计面板'}
        </Button>
        {live && (
          <Button
            size="sm"
            variant="danger"
            onClick={onEnd}
            title="agent 没有「只打断这一轮」的接口，停止会结束整个对话进程"
          >
            结束对话
          </Button>
        )}
      </div>
    </header>
  )
}

const SUGGESTIONS = [
  '读一遍 README，用三句话总结这个项目在做什么',
  '跑一遍测试，把失败的用例列出来',
  '找出仓库里最长的三个 Python 文件，说说它们各自的职责',
]

function EmptyChat({
  workspace,
  restoring,
  onPick,
}: {
  workspace: string
  restoring: boolean
  onPick: (text: string) => void
}) {
  if (restoring) {
    return <p className="py-16 text-center text-body text-ink-3">正在接回上一个对话…</p>
  }
  return (
    <div className="py-12 text-center">
      <MarkGlyph />
      <h2 className="mt-5 text-title font-semibold text-ink">开始一段对话</h2>
      <p className="mx-auto mt-2 max-w-md text-body text-ink-2">
        agent 会在工作区 <span className="font-mono text-ink">{workspace}</span> 里真实读写文件、
        跑测试和 lint。每一步都写进 append-only 的会话日志，事后可以逐条回放。
      </p>
      <p className="mx-auto mt-2 max-w-md text-caption text-ink-3">
        同一段对话里的多轮共享上下文——第二轮记得第一轮做过什么。
      </p>
      <div className="mt-6 space-y-2">
        {SUGGESTIONS.map((text) => (
          <button
            key={text}
            type="button"
            onClick={() => onPick(text)}
            className="surface-raised focus-ring block w-full rounded-card px-4 py-2.5 text-left text-caption text-ink-2 transition-colors hover:text-ink"
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  )
}

function Composer({
  draft,
  onDraft,
  onSubmit,
  disabled,
  busy,
  live,
  workspace,
  error,
  settings,
}: {
  draft: string
  onDraft: (value: string) => void
  onSubmit: () => void
  disabled: boolean
  busy: boolean
  live: boolean
  workspace: string
  error: string | null
  settings: React.ReactNode
}) {
  const box = useRef<HTMLTextAreaElement>(null)

  // 随内容长高，到 12rem 封顶后转成内部滚动。
  useEffect(() => {
    const node = box.current
    if (!node) return
    node.style.height = 'auto'
    node.style.height = `${Math.min(node.scrollHeight, 192)}px`
  }, [draft])

  return (
    <div className="divider-soft shrink-0 border-t bg-canvas">
      <div className="mx-auto w-full max-w-[46rem] px-6 py-4">
        {settings}
        {error && <p className="mb-2 text-caption text-red-ink">{error}</p>}
        <div className="surface-raised flex items-end gap-2 rounded-card px-3 py-2.5 transition-shadow focus-within:shadow-raised">
          <textarea
            ref={box}
            value={draft}
            onChange={(event) => onDraft(event.target.value)}
            onKeyDown={(event) => {
              // Enter 发送、Shift+Enter 换行——聊天框的通用约定。
              // 输入法组字期间的 Enter 是在选词，绝不能当成发送。
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault()
                onSubmit()
              }
            }}
            rows={1}
            placeholder={
              busy ? '这一轮还在跑，等它结束再发下一句…' : `在 ${workspace} 里要做什么？`
            }
            className="max-h-48 flex-1 resize-none bg-transparent py-1 text-body text-ink placeholder:text-ink-4 focus:outline-none"
          />
          <Button variant="primary" onClick={onSubmit} disabled={disabled || !draft.trim()}>
            {busy ? '执行中' : live ? '发送' : '开始'}
          </Button>
        </div>
        <p className="mt-1.5 text-micro text-ink-4">
          Enter 发送 · Shift+Enter 换行
          {live && ' · 多轮共享上下文，agent 记得前面几轮'}
        </p>
      </div>
    </div>
  )
}

function SettingsBar({
  meta,
  locked,
  open,
  onToggle,
  provider,
  onProvider,
  model,
  onModel,
  options,
  onOptions,
  missingKey,
}: {
  meta: MetaResponse
  locked: boolean
  open: boolean
  onToggle: () => void
  provider: string
  onProvider: (value: string) => void
  model: string
  onModel: (value: string) => void
  options: RunOptions
  onOptions: (update: (old: RunOptions) => RunOptions) => void
  missingKey: string
}) {
  const behaviors = meta.capabilities.filter((item) => item.category === 'behavior')
  const guardrails = meta.capabilities.filter((item) => item.category === 'guardrail')
  const tunings = meta.capabilities.filter((item) => item.category === 'tuning')

  return (
    <div className="mb-2">
      <div className="flex flex-wrap items-center gap-2 text-micro text-ink-3">
        <button
          type="button"
          onClick={onToggle}
          className="focus-ring rounded font-medium text-ink-2 transition-colors hover:text-ink"
          aria-expanded={open}
        >
          {open ? '收起设置' : '运行设置'}
        </button>
        <span className="font-mono text-ink-4">
          {provider}
          {model ? ` / ${model}` : ''}
        </span>
        {locked && <span className="text-ink-4">· 对话进行中，设置已锁定</span>}
      </div>

      {missingKey && !locked && (
        <p className="mt-1.5 text-micro text-orange-ink">
          环境里没有 {missingKey}，这次对话会直接失败。在 .env 里配好后重启服务。
        </p>
      )}

      {open && (
        <div className="surface-raised mt-2 space-y-4 rounded-card px-4 py-3.5">
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-micro font-medium text-ink-2">供应商</span>
              <select
                value={provider}
                onChange={(event) => onProvider(event.target.value)}
                disabled={locked}
                className="field focus-ring py-1.5 text-caption"
              >
                {meta.providers.map((item) => (
                  <option key={item.name} value={item.name}>
                    {item.name}
                    {item.api_key_present ? '' : '（未配 key）'}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-micro font-medium text-ink-2">模型</span>
              <input
                value={model}
                onChange={(event) => onModel(event.target.value)}
                disabled={locked}
                placeholder={meta.providers.find((item) => item.name === provider)?.model ?? ''}
                className="field focus-ring py-1.5 font-mono text-caption"
              />
            </label>
          </div>

          <Section title="行为开关" hint="研究性能力，默认全关，逐个打开做对照实验。">
            {behaviors.map((item) => (
              <Toggle
                key={item.key}
                info={item}
                value={Boolean(options[item.key] ?? item.default)}
                disabled={locked}
                onChange={(value) => onOptions((old) => ({ ...old, [item.key]: value }))}
              />
            ))}
          </Section>

          <Section title="护栏" hint="默认全开，一般不用动。">
            {guardrails.map((item) =>
              item.kind === 'bool' ? (
                <Toggle
                  key={item.key}
                  info={item}
                  value={Boolean(options[item.key] ?? item.default)}
                  disabled={locked}
                  onChange={(value) => onOptions((old) => ({ ...old, [item.key]: value }))}
                />
              ) : (
                <NumberField
                  key={item.key}
                  info={item}
                  value={options[item.key]}
                  disabled={locked}
                  onChange={(value) => onOptions((old) => ({ ...old, [item.key]: value }))}
                />
              ),
            )}
          </Section>

          <Section title="数值参数">
            {tunings.map((item) => (
              <NumberField
                key={item.key}
                info={item}
                value={options[item.key]}
                disabled={locked}
                onChange={(value) => onOptions((old) => ({ ...old, [item.key]: value }))}
              />
            ))}
          </Section>
        </div>
      )}
    </div>
  )
}

function Section({
  title,
  hint,
  children,
}: {
  title: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <section>
      <h3 className="text-micro font-semibold text-ink">{title}</h3>
      {hint && <p className="mt-0.5 mb-1.5 text-micro text-ink-4">{hint}</p>}
      <div className="space-y-0.5">{children}</div>
    </section>
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
      className="flex cursor-pointer items-center gap-3 rounded-control px-1.5 py-1.5 transition-colors hover:bg-muted"
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
    <label className="flex items-center gap-3 px-1.5 py-1.5" title={info.help}>
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

/**
 * 审计抽屉。
 *
 * 对话界面把过程收了起来，所以必须给一个「看原文」的出口——否则这个项目最核心的
 * 卖点就被好看的气泡盖住了。这里显示的就是磁盘上会话日志里的那一条。
 */
function Inspector({ entry, onClose }: { entry: SessionEntry | null; onClose: () => void }) {
  return (
    <aside className="divider-soft flex w-[22rem] shrink-0 flex-col border-l bg-subtle">
      <header className="divider-soft flex shrink-0 items-center justify-between gap-2 border-b px-4 py-3">
        <div className="min-w-0">
          <h2 className="truncate text-caption font-semibold text-ink">
            {entry ? `条目 ${entry.id}` : '审计面板'}
          </h2>
          {entry && <p className="truncate font-mono text-micro text-ink-3">{entry.event}</p>}
        </div>
        <Button size="sm" variant="ghost" onClick={onClose}>
          关闭
        </Button>
      </header>
      <div className="min-h-0 flex-1 overflow-auto px-4 py-3">
        {entry ? (
          <>
            <dl className="mb-3 space-y-1 text-micro">
              <Row label="parent" value={entry.parent_id || '（根）'} />
              <Row label="run id" value={entry.run_id} />
              <Row label="时间" value={entry.timestamp} />
            </dl>
            <div className="divider-soft border-t pt-3 font-mono text-micro">
              <JsonView value={entry.payload} />
            </div>
          </>
        ) : (
          <p className="text-caption text-ink-3">
            展开某一轮的「执行过程」，点其中一条，这里会显示它在会话日志里的完整原文。
            对话界面把过程折了起来，但一条证据都没有少。
          </p>
        )}
      </div>
    </aside>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <dt className="w-14 shrink-0 text-ink-4">{label}</dt>
      <dd className="min-w-0 flex-1 font-mono break-all text-ink-2">{value}</dd>
    </div>
  )
}

/** 空状态的极简标记。纯 SVG，不引任何外部资源。 */
function MarkGlyph() {
  return (
    <svg
      width="44"
      height="44"
      viewBox="0 0 44 44"
      fill="none"
      aria-hidden="true"
      className="mx-auto text-ink-4"
    >
      <rect x="4" y="8" width="36" height="24" rx="6" stroke="currentColor" strokeWidth="1.5" />
      <path d="M14 36l6-4M30 36l-6-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path
        d="M12 17h8M12 23h14"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  )
}
