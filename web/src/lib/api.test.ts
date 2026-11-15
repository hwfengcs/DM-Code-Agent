import { beforeEach, expect, it, vi } from 'vitest'
import { ApiError, api, fetchAllEntries, subscribeToConversation, type StreamEvent } from './api'

class FakeEventSource {
  static CLOSED = 2
  readyState = 1
  listeners = new Map<string, (event: Event) => void>()
  close = vi.fn(() => { this.readyState = FakeEventSource.CLOSED })

  addEventListener(name: string, callback: (event: Event) => void): void {
    this.listeners.set(name, callback)
  }
}

let source: FakeEventSource

beforeEach(() => {
  vi.stubGlobal('sessionStorage', { getItem: () => null })
  source = new FakeEventSource()
  const Constructor = function () { return source }
  Constructor.CLOSED = FakeEventSource.CLOSED
  vi.stubGlobal('EventSource', Constructor)
})

it('surfaces a server error frame and stops reconnecting to that terminal stream', () => {
  const events: StreamEvent[] = []
  subscribeToConversation('conversation-1', (event) => events.push(event))
  source.listeners.get('error')?.(new MessageEvent('error', {
    data: JSON.stringify({ message: '等待 30s 仍未生成会话日志。' }),
  }))
  expect(events).toEqual([{ kind: 'error', message: '等待 30s 仍未生成会话日志。' }])
  expect(source.close).toHaveBeenCalledOnce()
})

it('leaves transient network errors to EventSource automatic reconnect', () => {
  const events: StreamEvent[] = []
  subscribeToConversation('conversation-1', (event) => events.push(event))
  source.listeners.get('error')?.(new Event('error'))
  expect(source.close).not.toHaveBeenCalled()
  expect(events).toEqual([])
})

it('fills in the envelope of a streamed line that is not a session entry', () => {
  const events: StreamEvent[] = []
  subscribeToConversation('conversation-1', (event) => events.push(event))
  source.listeners.get('entry')?.(new MessageEvent('entry', {
    data: JSON.stringify({ id: 'a-0001', instance_id: 'foreign' }), lastEventId: '3',
  }))
  expect(events).toEqual([{
    kind: 'entry', lineIndex: 3,
    entry: {
      id: 'a-0001', parent_id: '', timestamp: '', run_id: '', event: '', payload: {},
      instance_id: 'foreign',
    },
  }])
})

/** 让 `/api/sessions/entries` 按 offset 分页返回 `lines`，每页最多 `pageSize` 条。 */
function stubEntryPages(lines: Record<string, unknown>[], pageSize: number) {
  const fetchMock = vi.fn(async (url: string) => {
    const offset = Number(new URL(url, 'http://localhost').searchParams.get('offset'))
    const entries = lines.slice(offset, offset + pageSize)
    return new Response(JSON.stringify({ name: 'x.jsonl', total: lines.length, offset, limit: pageSize, entries }))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

it('normalizes entries on both the single-page and the paged return path', async () => {
  const lines = [{ id: 'legacy-0000' }, { id: 'legacy-0001' }, { id: 'legacy-0002' }]
  const expected = lines.map((line) => ({
    ...line, parent_id: '', timestamp: '', run_id: '', event: '', payload: {},
  }))

  const singlePage = stubEntryPages(lines, 1000)
  expect((await fetchAllEntries('x.jsonl')).entries).toEqual(expected)
  expect(singlePage).toHaveBeenCalledTimes(1)

  const paged = stubEntryPages(lines, 2)
  expect((await fetchAllEntries('x.jsonl')).entries).toEqual(expected)
  expect(paged).toHaveBeenCalledTimes(2)
})

it('reports request validation errors as their messages instead of raw JSON', async () => {
  // FastAPI 的 422：detail 是数组，每项的 msg 才是给人看的那句。
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
    detail: [
      { type: 'too_long', loc: ['body', 'names'], msg: 'List should have at most 200 items', input: [] },
      { type: 'missing', loc: ['body', 'task'], msg: 'Field required', input: {} },
    ],
  }), { status: 422 })))

  const failure = await api.deleteSessions(['a.jsonl']).catch((cause: unknown) => cause)

  expect(failure).toBeInstanceOf(ApiError)
  expect((failure as ApiError).status).toBe(422)
  expect((failure as ApiError).message).toBe('List should have at most 200 items；Field required')
})
