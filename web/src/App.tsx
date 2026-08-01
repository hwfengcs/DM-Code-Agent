import { useCallback, useEffect, useState } from 'react'
import { ApiError, api, bootstrapToken, setToken } from './lib/api'
import { useRoute } from './lib/router'
import { restoreConversation, useConversation } from './lib/conversationStore'
import type { MetaResponse, SessionListResponse } from './lib/types'
import { Button, ErrorBox, Spinner } from './components/ui'
import { Sidebar } from './components/Sidebar'
import { SessionList } from './views/SessionList'
import { RunDetail } from './views/RunDetail'
import { DiffView } from './views/DiffView'
import { Chat } from './views/Chat'

export function App() {
  const [route] = useRoute()
  const [meta, setMeta] = useState<MetaResponse | null>(null)
  const [sessions, setSessions] = useState<SessionListResponse | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  // diff 的基准会话。放在顶层是因为它要跨「会话库」和「运行详情」两个视图存活。
  const [compareWith, setCompareWith] = useState<string | null>(null)
  const conversation = useConversation()

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

  const refreshSessions = useCallback(async () => {
    try {
      setSessions(await api.sessions())
    } catch {
      // 列表刷新失败不该顶掉整个界面——下次操作会再试。
    }
  }, [])

  useEffect(() => {
    bootstrapToken()
    void load()
  }, [load])

  // 页面加载时接回上一个还活着的对话。放在 App 而不是 Chat 里，
  // 是为了让「刷新后落在会话库」这种路径也能恢复，侧栏的活跃指示才不会说谎。
  useEffect(() => {
    if (meta && !meta.server.read_only) void restoreConversation()
  }, [meta])

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

  // 只读展厅里对话不可用，把默认路由让给会话库——它本来就是只读模式的全部价值。
  const effective = route.name === 'chat' && meta.server.read_only ? { name: 'list' as const } : route

  return (
    <div className="flex h-full min-h-0">
      <Sidebar
        route={effective}
        meta={meta}
        sessionCount={sessions.aggregate.total}
        compareWith={compareWith}
        conversation={conversation.record}
      />
      <main className="flex min-h-0 min-w-0 flex-1 flex-col">
        {effective.name === 'chat' && (
          <Chat meta={meta} onSessionsChanged={() => void refreshSessions()} />
        )}
        {effective.name === 'list' && (
          <SessionList
            data={sessions}
            readOnly={meta.server.read_only}
            compareWith={compareWith}
            onCompareWith={setCompareWith}
            onRefresh={() => void load()}
          />
        )}
        {effective.name === 'run' && (
          <RunDetail
            session={effective.session}
            readOnly={meta.server.read_only}
            compareWith={compareWith}
            onCompareWith={setCompareWith}
            onSessionCreated={() => void load()}
          />
        )}
        {effective.name === 'diff' && <DiffView a={effective.a} b={effective.b} />}
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
