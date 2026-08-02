/**
 * 对话的全局状态。
 *
 * **这是「切页面运行就停了」那个 bug 的正解。**
 *
 * 上一版把运行状态和 SSE 订阅都放在 `NewRun` 组件里，`useEffect` 的清理函数在组件
 * 卸载时断流。于是切到会话库再切回来，条目、状态、连接全没了——看起来就像运行被
 * 中断了（实际上服务端子进程一直好好活着，只是前端把自己的眼睛闭上了）。
 *
 * 这里改成模块级单例：
 *
 * * 订阅的生命周期跟着**对话**走，不跟着组件走。切视图、开关抽屉都不影响它。
 * * `conversationId` 落 sessionStorage，刷新页面后自动重连——后端进程还活着，
 *   `Last-Event-ID` 负责把断线期间的条目补回来。
 * * 用 `useSyncExternalStore` 订阅，React 18/19 的并发渲染下不会读到撕裂的状态。
 */
import { useSyncExternalStore } from 'react'
import { ApiError, api, subscribeToConversation, type RunOptions } from './api'
import type { ConversationRecord, SessionEntry } from './types'

const STORAGE_KEY = 'dm-agent-console-conversation'

export interface ConversationState {
  /** 还没开对话时为 null。 */
  record: ConversationRecord | null
  entries: SessionEntry[]
  /** 正在建对话 / 正在投递一轮。用来禁用输入框。 */
  pending: boolean
  /** 一次性提示（连接断了、投递被拒等）。 */
  notice: string | null
  error: string | null
  /** 页面加载时正在尝试重连一个已有对话。 */
  restoring: boolean
}

const EMPTY: ConversationState = {
  record: null,
  entries: [],
  pending: false,
  notice: null,
  error: null,
  restoring: false,
}

let state: ConversationState = EMPTY
let unsubscribe: (() => void) | null = null
const listeners = new Set<() => void>()

function emit(): void {
  for (const listener of listeners) listener()
}

function set(patch: Partial<ConversationState>): void {
  state = { ...state, ...patch }
  emit()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function snapshot(): ConversationState {
  return state
}

/** 订阅整个对话状态。组件卸载只是退订，**不会**动 SSE 连接。 */
export function useConversation(): ConversationState {
  return useSyncExternalStore(subscribe, snapshot, snapshot)
}

function describe(cause: unknown): string {
  if (cause instanceof ApiError) return cause.message
  return cause instanceof Error ? cause.message : String(cause)
}

function attach(conversationId: string): void {
  unsubscribe?.()
  unsubscribe = subscribeToConversation(conversationId, (event) => {
    switch (event.kind) {
      case 'status':
        set({ record: event.record as ConversationRecord })
        break
      case 'entry':
        // 按 id 去重：断线重连时 Last-Event-ID 之前的条目可能被重发。
        set({
          entries: state.entries.some((item) => item.id === event.entry.id)
            ? state.entries
            : [...state.entries, event.entry],
        })
        break
      case 'malformed':
        set({ notice: `会话日志第 ${event.lineIndex} 行无法解析，已跳过。` })
        break
      case 'done':
        set({ record: event.record as ConversationRecord })
        break
      case 'error':
        set({ notice: event.message })
        break
    }
  })
}

/**
 * 拉一次状态，把 `record` 与实际情况对齐。
 *
 * SSE 的 `status` 事件只在连接建立时发一次，而轮次状态（busy / completed_turns）
 * 会随每一轮变化。所以每次投递前后都主动对一次表。
 */
async function refresh(conversationId: string): Promise<void> {
  try {
    set({ record: await api.conversation(conversationId) })
  } catch (cause) {
    set({ notice: describe(cause) })
  }
}

/** 开一个新对话。已有对话会被先结束掉——同时跑两个 agent 一定互相踩工作区。 */
export async function startConversation(body: {
  provider: string
  model: string
  options: RunOptions
}): Promise<boolean> {
  set({ pending: true, error: null, notice: null })
  try {
    if (state.record?.run_id && state.record.status !== 'cancelled') {
      await api.endConversation(state.record.run_id).catch(() => undefined)
    }
    const created = await api.createConversation(body)
    sessionStorage.setItem(STORAGE_KEY, created.run_id)
    set({ record: created, entries: [], pending: false })
    attach(created.run_id)
    return true
  } catch (cause) {
    set({ pending: false, error: describe(cause) })
    return false
  }
}

/** 投递一轮任务。上一轮没跑完时后端会 409，这里把原因原样透出来。 */
export async function sendTurn(task: string): Promise<boolean> {
  const conversationId = state.record?.run_id
  if (!conversationId) return false
  set({ pending: true, notice: null })
  try {
    const result = await api.submitTurn(conversationId, task)
    set({ record: result.conversation, pending: false })
    // 后端刚收下这一轮，busy 还没翻上来；对一次表让输入框立刻进入禁用态。
    void refresh(conversationId)
    return true
  } catch (cause) {
    set({ pending: false, notice: describe(cause) })
    return false
  }
}

/** 结束整个对话。**不是**只打断当前这一轮——`ReactAgent` 没有取消接口。 */
export async function endConversation(): Promise<void> {
  const conversationId = state.record?.run_id
  if (!conversationId) return
  set({ pending: true })
  try {
    set({ record: await api.endConversation(conversationId), pending: false })
  } catch (cause) {
    set({ pending: false, notice: describe(cause) })
  }
}

/** 从界面上清掉当前对话（不动服务端；已结束的对话才有意义）。 */
export function clearConversation(): void {
  unsubscribe?.()
  unsubscribe = null
  sessionStorage.removeItem(STORAGE_KEY)
  state = EMPTY
  emit()
}

export function dismissNotice(): void {
  set({ notice: null })
}

/**
 * 页面加载时尝试接回上一个对话。
 *
 * 只在服务端确认它**还活着**时才接：进程已经退出的对话没有继续对话的意义，
 * 用户应该去会话库里以历史记录的形式审计它。
 */
export async function restoreConversation(): Promise<void> {
  const conversationId = sessionStorage.getItem(STORAGE_KEY)
  if (!conversationId || state.record) return
  set({ restoring: true })
  try {
    const record = await api.conversation(conversationId)
    if (record.status === 'idle' || record.status === 'running') {
      set({ record, entries: [], restoring: false })
      attach(conversationId)
      return
    }
    sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // 404（控制台重启过）或网络问题：安静地放弃，用户重新开一个就是。
    sessionStorage.removeItem(STORAGE_KEY)
  }
  set({ restoring: false })
}
