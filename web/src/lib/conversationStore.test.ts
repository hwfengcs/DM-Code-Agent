import { beforeEach, expect, it, vi } from 'vitest'
import * as apiModule from './api'
import { clearConversation, restoreConversation, sendTurn, startConversation, useConversation } from './conversationStore'
import type { ConversationRecord } from './types'

vi.mock('react', () => ({
  useSyncExternalStore: (_subscribe: unknown, getSnapshot: () => unknown) => getSnapshot(),
}))

const record: ConversationRecord = {
  run_id: 'chat-1', task: '', session: 'chat-1.jsonl', status: 'idle', agent_status: '',
  started_at: 0, finished_at: null, exit_code: null, cancelled: false, error: '', pid: 1,
  kind: 'conversation', turns: [], submitted_turns: 0, completed_turns: 0, busy: false,
  last_activity: 0,
}

let onEvent: (event: apiModule.StreamEvent) => void

beforeEach(() => {
  const storage = new Map<string, string>()
  vi.stubGlobal('sessionStorage', {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
  })
  clearConversation()
  vi.restoreAllMocks()
  vi.spyOn(apiModule.api, 'createConversation').mockResolvedValue(record)
  vi.spyOn(apiModule.api, 'endConversation').mockResolvedValue({ ...record, stopped: true })
  vi.spyOn(apiModule, 'subscribeToConversation').mockImplementation((_id, callback) => {
    onEvent = callback
    return () => undefined
  })
})

it('refreshes busy state after run_end so the next turn can be submitted', async () => {
  const busy = { ...record, status: 'running' as const, busy: true, submitted_turns: 1 }
  vi.spyOn(apiModule.api, 'submitTurn').mockResolvedValue({
    turn: { index: 1, task: 'first', submitted_at: 0 }, conversation: busy,
  })
  const refresh = vi.spyOn(apiModule.api, 'conversation').mockResolvedValue(busy)
  await startConversation({ provider: 'deepseek', model: '', options: {} })
  await sendTurn('first')
  expect(useConversation().record?.busy).toBe(true)

  refresh.mockResolvedValue({ ...record, submitted_turns: 1, completed_turns: 1 })
  onEvent({
    kind: 'entry', lineIndex: 1,
    entry: { id: 'end-1', parent_id: '', timestamp: '', run_id: 'chat-1',
      event: 'run_end', payload: { status: 'success' } },
  })
  await vi.waitFor(() => expect(useConversation().record?.busy).toBe(false))
  expect(useConversation().record?.completed_turns).toBe(1)
})

it.each([false, true])('ignores an old conversation refresh after a new conversation starts (fails=%s)', async (fails) => {
  let resolveRefresh: (value: ConversationRecord) => void = () => undefined
  let rejectRefresh: (cause: Error) => void = () => undefined
  vi.spyOn(apiModule.api, 'conversation').mockReturnValue(new Promise((resolve, reject) => {
    resolveRefresh = resolve
    rejectRefresh = reject
  }))
  await startConversation({ provider: 'deepseek', model: '', options: {} })
  onEvent({
    kind: 'entry', lineIndex: 1,
    entry: { id: 'end-1', parent_id: '', timestamp: '', run_id: 'chat-1',
      event: 'run_end', payload: { status: 'success' } },
  })
  vi.mocked(apiModule.api.createConversation).mockResolvedValue({ ...record, run_id: 'chat-2' })
  await startConversation({ provider: 'deepseek', model: '', options: {} })
  if (fails) rejectRefresh(new Error('old request failed'))
  else resolveRefresh(record)
  await Promise.resolve()
  expect(useConversation().record?.run_id).toBe('chat-2')
  expect(useConversation().notice).toBeNull()
})

it('does not restore an old conversation over a newly started one', async () => {
  sessionStorage.setItem('dm-agent-console-conversation', record.run_id)
  let resolveRestore: (value: ConversationRecord) => void = () => undefined
  vi.spyOn(apiModule.api, 'conversation').mockReturnValue(new Promise((resolve) => {
    resolveRestore = resolve
  }))
  const restoring = restoreConversation()
  vi.mocked(apiModule.api.createConversation).mockResolvedValue({ ...record, run_id: 'chat-2' })
  await startConversation({ provider: 'deepseek', model: '', options: {} })
  resolveRestore(record)
  await restoring

  expect(useConversation().record?.run_id).toBe('chat-2')
  expect(useConversation().restoring).toBe(false)
  expect(sessionStorage.getItem('dm-agent-console-conversation')).toBe('chat-2')
})

it('does not erase a new conversation identifier when an old restore fails', async () => {
  sessionStorage.setItem('dm-agent-console-conversation', record.run_id)
  let rejectRestore: (cause: Error) => void = () => undefined
  vi.spyOn(apiModule.api, 'conversation').mockReturnValue(new Promise((_resolve, reject) => {
    rejectRestore = reject
  }))
  const restoring = restoreConversation()
  vi.mocked(apiModule.api.createConversation).mockResolvedValue({ ...record, run_id: 'chat-2' })
  await startConversation({ provider: 'deepseek', model: '', options: {} })
  rejectRestore(new Error('old request failed'))
  await restoring

  expect(sessionStorage.getItem('dm-agent-console-conversation')).toBe('chat-2')
})
