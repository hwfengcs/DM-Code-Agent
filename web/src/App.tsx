import { useCallback, useEffect, useState } from 'react'
import { ApiError, api, bootstrapToken, setToken } from './lib/api'
import { hrefFor, useRoute } from './lib/router'
import type { MetaResponse, SessionListResponse } from './lib/types'
import { Button, ErrorBox, Spinner } from './components/ui'
import { SessionList } from './views/SessionList'
import { RunDetail } from './views/RunDetail'
import { DiffView } from './views/DiffView'
import { NewRun } from './views/NewRun'

export function App() {
  const [route] = useRoute()
  const [meta, setMeta] = useState<MetaResponse | null>(null)
  const [sessions, setSessions] = useState<SessionListResponse | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  // diff 的基准会话。放在顶层是因为它要跨「会话库」和「运行详情」两个视图存活。
  const [compareWith, setCompareWith] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const [metaResponse, sessionsResponse] = await Promise.all([api.meta(), api.sessions()])
      setMeta(metaResponse)
      setSessions(sessionsResponse)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause : new ApiError(0, String(cause)))
    }
  }, [])

  useEffect(() => {
    bootstrapToken()
    void load()
  }, [load])

  if (error?.isAuthError) return <TokenPrompt onSubmit={load} />
  if (error) {
    return (
      <ErrorBox
        title="连不上后端"
        detail={error.message}
        action={<Button onClick={() => void load()}>重试</Button>}
      />
    )
  }
  if (!meta || !sessions) return <Spinner label="连接控制台" />

  return (
    <div className="relative z-10 flex h-full min-h-0 flex-col">
      <TopBar meta={meta} compareWith={compareWith} onRefresh={() => void load()} />
      <main className="min-h-0 flex-1 overflow-hidden">
        {route.name === 'list' && (
          <SessionList data={sessions} compareWith={compareWith} onCompareWith={setCompareWith} />
        )}
        {route.name === 'run' && (
          <RunDetail
            session={route.session}
            readOnly={meta.server.read_only}
            compareWith={compareWith}
            onSessionCreated={() => void load()}
          />
        )}
        {route.name === 'diff' && <DiffView a={route.a} b={route.b} />}
        {route.name === 'new' && <NewRun meta={meta} onFinished={() => void load()} />}
      </main>
    </div>
  )
}

function TopBar({
  meta,
  compareWith,
  onRefresh,
}: {
  meta: MetaResponse
  compareWith: string | null
  onRefresh: () => void
}) {
  return (
    <header className="flex shrink-0 items-center gap-4 border-b border-scope-line bg-scope-panel/80 px-4 py-2 backdrop-blur">
      <a href="#/" className="flex items-baseline gap-2">
        <span className="font-mono text-sm text-scope-text">DM-Code-Agent</span>
        <span className="meta-label">控制台 v{meta.version}</span>
      </a>

      <span
        className={`chip ${
          meta.server.read_only
            ? 'border-signal-info/40 bg-signal-info/10 text-signal-info'
            : 'border-signal-warn/40 bg-signal-warn/10 text-signal-warn'
        }`}
        title={
          meta.server.read_only
            ? '只读模式：只提供审计能力，不能发起运行或分叉'
            : `完整模式：agent 会在 ${meta.server.workspace} 里真实读写文件`
        }
      >
        {meta.server.read_only ? '只读' : '可写'}
      </span>

      {compareWith && (
        <span className="chip border-scope-line bg-scope-raised text-scope-dim">
          diff 基准 {compareWith}
        </span>
      )}

      <div className="ml-auto flex items-center gap-2">
        <span className="hidden font-mono text-[11px] text-scope-faint sm:inline">
          {meta.server.workspace}
        </span>
        {!meta.server.read_only && (
          <a
            href={hrefFor({ name: 'new' })}
            className="focus-ring rounded border border-signal-info/50 bg-signal-info/10 px-2 py-1 font-mono text-[11px] text-signal-info"
          >
            + 新建运行
          </a>
        )}
        <Button onClick={onRefresh}>刷新</Button>
      </div>
    </header>
  )
}

function TokenPrompt({ onSubmit }: { onSubmit: () => void }) {
  const [value, setValue] = useState('')
  return (
    <div className="relative z-10 flex h-full items-center justify-center p-6">
      <div className="panel w-full max-w-md p-6">
        <h1 className="font-mono text-sm text-scope-text">需要访问 token</h1>
        <p className="mt-2 text-xs text-scope-dim">
          启动 <code className="rounded bg-scope-raised px-1 font-mono">dm-agent-web</code>{' '}
          时终端里打印了一条带 token 的地址，直接点开那条地址即可；或者把 token 粘贴到下面。
        </p>
        <form
          className="mt-4 flex gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            setToken(value.trim())
            onSubmit()
          }}
        >
          <input
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="粘贴 token"
            className="focus-ring flex-1 rounded border border-scope-line bg-scope-bg px-2 py-1.5 font-mono text-xs text-scope-text"
          />
          <Button variant="primary">连接</Button>
        </form>
      </div>
    </div>
  )
}
