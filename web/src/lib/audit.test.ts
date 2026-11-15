import { expect, it } from 'vitest'
import { parseHash } from './router'
import { splitTurns } from './turns'
import type { SessionEntry } from './types'

const entry = (id: string, event: string): SessionEntry => ({
  id, event, parent_id: '', run_id: 'r', timestamp: '', payload: {},
})

it('opens the session list for malformed percent escapes', () => {
  expect(parseHash('#/run/%zz')).toEqual({ name: 'list' })
})

it('distinguishes active work from an interrupted historical run', () => {
  const entries = [entry('a', 'run_start')]
  expect(splitTurns(entries, true)[0]?.running).toBe(true)
  expect(splitTurns(entries, false)[0]?.status).toBe('interrupted')
  expect(splitTurns([...entries, entry('b', 'conversation_end')], true)[0]?.running).toBe(false)
})
