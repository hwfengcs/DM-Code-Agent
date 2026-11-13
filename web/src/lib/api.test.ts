import { beforeEach, expect, it, vi } from 'vitest'
import { subscribeToRun, type StreamEvent } from './api'

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
  subscribeToRun('run-1', (event) => events.push(event))
  source.listeners.get('error')?.(new MessageEvent('error', {
    data: JSON.stringify({ message: '等待 30s 仍未生成会话日志。' }),
  }))
  expect(events).toEqual([{ kind: 'error', message: '等待 30s 仍未生成会话日志。' }])
  expect(source.close).toHaveBeenCalledOnce()
})

it('leaves transient network errors to EventSource automatic reconnect', () => {
  const events: StreamEvent[] = []
  subscribeToRun('run-1', (event) => events.push(event))
  source.listeners.get('error')?.(new Event('error'))
  expect(source.close).not.toHaveBeenCalled()
  expect(events).toEqual([])
})
