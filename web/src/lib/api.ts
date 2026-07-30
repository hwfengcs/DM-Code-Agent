/**
 * 后端 API 客户端。
 *
 * token 处理：服务端启动时打印的地址带 `?token=...`。首次加载时把它取出来存进
 * sessionStorage 并**从地址栏抹掉**，之后一律用 Authorization 头发送——避免 token
 * 长期留在地址栏里被截图、被写进浏览器历史。
 */
import type {
  DiffResponse,
  EntriesResponse,
  ForkResponse,
  MetaResponse,
  RunRecord,
  SessionAnalysis,
  SessionEntry,
  SessionListResponse,
  SessionSummary,
} from './types'

const TOKEN_STORAGE_KEY = 'dm-agent-console-token'

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }

  /** 401 要引导用户回去看服务端打印的那条带 token 的地址。 */
  get isAuthError(): boolean {
    return this.status === 401
  }
}

function readTokenFromLocation(): string | null {
  // token 可能在 ?token= 也可能在 #/path?token=（hash 路由下）。两处都看。
  const fromSearch = new URLSearchParams(window.location.search).get('token')
  if (fromSearch) return fromSearch
  const hash = window.location.hash
  const queryStart = hash.indexOf('?')
  if (queryStart >= 0) {
    return new URLSearchParams(hash.slice(queryStart + 1)).get('token')
  }
  return null
}

function stripTokenFromLocation(): void {
  const url = new URL(window.location.href)
  url.searchParams.delete('token')
  const hash = url.hash
  const queryStart = hash.indexOf('?')
  if (queryStart >= 0) {
    const params = new URLSearchParams(hash.slice(queryStart + 1))
    params.delete('token')
    const rest = params.toString()
    url.hash = rest ? `${hash.slice(0, queryStart)}?${rest}` : hash.slice(0, queryStart)
  }
  window.history.replaceState(null, '', url.toString())
}

export function bootstrapToken(): string {
  const fromUrl = readTokenFromLocation()
  if (fromUrl) {
    sessionStorage.setItem(TOKEN_STORAGE_KEY, fromUrl)
    stripTokenFromLocation()
    return fromUrl
  }
  return sessionStorage.getItem(TOKEN_STORAGE_KEY) ?? ''
}

export function setToken(token: string): void {
  sessionStorage.setItem(TOKEN_STORAGE_KEY, token)
}

export function getToken(): string {
  return sessionStorage.getItem(TOKEN_STORAGE_KEY) ?? ''
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken()
  const headers = new Headers(init?.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init?.body) headers.set('Content-Type', 'application/json')

  let response: Response
  try {
    response = await fetch(`/api${path}`, { ...init, headers })
  } catch (cause) {
    throw new ApiError(0, `连不上后端：${String(cause)}`)
  }

  if (!response.ok) {
    throw new ApiError(response.status, await describeFailure(response))
  }
  return (await response.json()) as T
}

async function describeFailure(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
    return JSON.stringify(body.detail ?? body)
  } catch {
    return `HTTP ${response.status}`
  }
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value))
  }
  const rendered = search.toString()
  return rendered ? `?${rendered}` : ''
}

export const api = {
  meta: () => request<MetaResponse>('/meta'),
  sessions: () => request<SessionListResponse>('/sessions'),
  summary: (name: string) =>
    request<{ name: string; summary: SessionSummary }>(`/sessions/summary${query({ name })}`),
  analysis: (name: string) =>
    request<{ name: string; analysis: SessionAnalysis }>(`/sessions/analysis${query({ name })}`),
  entries: (name: string, offset = 0, limit = 1000) =>
    request<EntriesResponse>(`/sessions/entries${query({ name, offset, limit })}`),
  diff: (a: string, b: string) => request<DiffResponse>(`/sessions/diff${query({ a, b })}`),
  fork: (name: string, at: string, output?: string) =>
    request<ForkResponse>('/sessions/fork', {
      method: 'POST',
      body: JSON.stringify({ name, at, output: output || null }),
    }),

  createRun: (body: { task: string; provider: string; model: string; options: RunOptions }) =>
    request<RunRecord>('/runs', { method: 'POST', body: JSON.stringify(body) }),
  runs: () => request<{ runs: RunRecord[] }>('/runs'),
  run: (runId: string) => request<RunRecord>(`/runs/${encodeURIComponent(runId)}`),
  cancelRun: (runId: string) =>
    request<RunRecord & { stopped: boolean }>(`/runs/${encodeURIComponent(runId)}`, {
      method: 'DELETE',
    }),
}

export type RunOptions = Record<string, boolean | number>

/** SSE 事件的判别联合。`entry` 的 data 就是一条会话条目原文。 */
export type StreamEvent =
  | { kind: 'status'; record: RunRecord }
  | { kind: 'entry'; entry: SessionEntry; lineIndex: number }
  | { kind: 'malformed'; lineIndex: number }
  | { kind: 'done'; record: RunRecord }
  | { kind: 'error'; message: string }

/**
 * 订阅一次运行的实时条目流。
 *
 * 用 ``EventSource`` 而不是手写 fetch 流：断线自动重连 + 自动带上 ``Last-Event-ID``
 * 都是浏览器免费给的，后端已按行号发 ``id:``，续传因此开箱可用。
 *
 * 代价是 EventSource 不能自定义请求头，所以 token 只能走查询参数——后端的
 * ``require_token`` 为此保留了 ``?token=`` 回退。
 */
export function subscribeToRun(
  runId: string,
  onEvent: (event: StreamEvent) => void,
): () => void {
  const token = getToken()
  const query = token ? `?token=${encodeURIComponent(token)}` : ''
  const source = new EventSource(`/api/runs/${encodeURIComponent(runId)}/stream${query}`)

  const parse = <T,>(raw: string): T | null => {
    try {
      return JSON.parse(raw) as T
    } catch {
      return null
    }
  }

  source.addEventListener('status', (event) => {
    const record = parse<RunRecord>((event as MessageEvent<string>).data)
    if (record) onEvent({ kind: 'status', record })
  })

  source.addEventListener('entry', (event) => {
    const message = event as MessageEvent<string>
    const entry = parse<SessionEntry>(message.data)
    if (entry) onEvent({ kind: 'entry', entry, lineIndex: Number(message.lastEventId) })
  })

  source.addEventListener('malformed', (event) => {
    const message = event as MessageEvent<string>
    onEvent({ kind: 'malformed', lineIndex: Number(message.lastEventId) })
  })

  source.addEventListener('done', (event) => {
    const record = parse<RunRecord>((event as MessageEvent<string>).data)
    if (record) onEvent({ kind: 'done', record })
    // 运行结束后不需要重连；不关的话 EventSource 会一直重试。
    source.close()
  })

  source.addEventListener('error', () => {
    // EventSource 会自动重连，所以这里不当作终态——只在 UI 上提示一下。
    if (source.readyState === EventSource.CLOSED) {
      onEvent({ kind: 'error', message: '实时连接已断开。' })
    }
  })

  return () => source.close()
}

/** 一次把整个会话的条目读完（后端按 1000 条一页）。 */
export async function fetchAllEntries(name: string): Promise<EntriesResponse> {
  const first = await api.entries(name, 0)
  if (first.entries.length >= first.total) return first
  const entries = [...first.entries]
  while (entries.length < first.total) {
    const page = await api.entries(name, entries.length)
    if (page.entries.length === 0) break
    entries.push(...page.entries)
  }
  return { ...first, entries, offset: 0, limit: entries.length }
}
