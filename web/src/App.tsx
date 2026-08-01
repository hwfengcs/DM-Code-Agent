import { useCallback, useEffect, useState } from 'react'
import { ApiError, api, bootstrapToken, setToken } from './lib/api'
import { useRoute } from './lib/router'
import type { MetaResponse, SessionListResponse } from './lib/types'
import { Button, ErrorBox, Spinner } from './components/ui'
import { Sidebar } from './components/Sidebar'
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
        action={
          <Button variant="primary" onClick={() => void load()}>
            重试
          </Button>
        }
      />
    )
  }
  if (!meta || !sessions) return <Spinner label="连接控制台" />

  return (
    <div className="flex h-full min-h-0">
      <Sidebar
        route={route}
        meta={meta}
        sessionCount={sessions.aggregate.total}
        compareWith={compareWith}
      />
      <main className="flex min-h-0 min-w-0 flex-1 flex-col">
        {route.name === 'list' && (
          <SessionList
            data={sessions}
            compareWith={compareWith}
            onCompareWith={setCompareWith}
            onRefresh={() => void load()}
          />
        )}
        {route.name === 'run' && (
          <RunDetail
            session={route.session}
            readOnly={meta.server.read_only}
            compareWith={compareWith}
            onCompareWith={setCompareWith}
            onSessionCreated={() => void load()}
          />
        )}
        {route.name === 'diff' && <DiffView a={route.a} b={route.b} />}
        {route.name === 'new' && <NewRun meta={meta} onFinished={() => void load()} />}
      </main>
    </div>
  )
}

function TokenPrompt({ onSubmit }: { onSubmit: () => void }) {
  const [value, setValue] = useState('')
  return (
    <div className="flex h-full items-center justify-center bg-subtle p-6">
      <div className="card w-full max-w-md p-8">
        <h1 className="text-title font-semibold text-ink">需要访问 token</h1>
        <p className="mt-2 text-caption text-ink-2">
          启动 <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-ink">dm-agent-web</code>{' '}
          时终端里打印了一条带 token 的地址，直接点开那条地址即可；或者把 token 粘贴到下面。
        </p>
        <form
          className="mt-5 flex gap-2"
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
            className="field focus-ring flex-1 font-mono"
          />
          <Button variant="primary" type="submit">
            连接
          </Button>
        </form>
      </div>
    </div>
  )
}
