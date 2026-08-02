/**
 * 条目流 → 对话轮次的单测。
 *
 * 与 `entries.test.ts` 同样的边界：只测分组与取值，不测任何诊断结论。
 * 这里最要紧的一条是 `test 多轮共存于一份日志`——它保证「一份 append-only 会话
 * 日志就足以表达整段多轮对话」，从而实时视图与历史审计视图可以共用一个渲染器。
 */
import { describe, expect, it } from 'vitest'
import {
  describeActivity,
  describeActivityEntry,
  labelActivityEntry,
  looksLikeConversation,
  splitTurns,
} from './turns'
import type { SessionEntry } from './types'

let seq = 0

function entry(event: string, payload: Record<string, unknown> = {}): SessionEntry {
  seq += 1
  return {
    id: `e-${String(seq).padStart(4, '0')}`,
    parent_id: seq > 1 ? `e-${String(seq - 1).padStart(4, '0')}` : '',
    timestamp: `2026-02-01T00:00:${String(seq % 60).padStart(2, '0')}+00:00`,
    run_id: 'chat-1',
    event,
    payload,
  }
}

/** 一段完整的轮次：用户提问 → 计划 → 工具 → step → 回答。 */
function turnEntries(task: string, answer: string, extra: SessionEntry[] = []): SessionEntry[] {
  return [
    entry('run_start', { task }),
    entry('plan', { steps: [{ step_number: 1, action: 'read_file' }] }),
    ...extra,
    entry('tool_call', { step_number: 1, action: 'read_file', observation: '读到了 12 行' }),
    entry('step', { step_number: 1, action: 'read_file', observation: '读到了 12 行' }),
    entry('run_end', { status: 'success', final_answer: answer }),
  ]
}

describe('splitTurns', () => {
  it('把一份日志切成对话轮次', () => {
    const turns = splitTurns([...turnEntries('第一问', '第一答'), ...turnEntries('第二问', '第二答')])

    expect(turns).toHaveLength(2)
    expect(turns.map((turn) => turn.index)).toEqual([1, 2])
    expect(turns.map((turn) => turn.task)).toEqual(['第一问', '第二问'])
    expect(turns.map((turn) => turn.answer)).toEqual(['第一答', '第二答'])
    expect(turns.every((turn) => turn.running === false)).toBe(true)
  })

  it('丢掉 run_start 之前的会话建立条目', () => {
    // runtime 属于「进程起来了」而不是任何一轮，混进第一轮会凭空多出噪音。
    const turns = splitTurns([entry('runtime', { provider: 'deepseek' }), ...turnEntries('问', '答')])
    expect(turns).toHaveLength(1)
    expect(turns[0]?.entries.some((item) => item.event === 'runtime')).toBe(false)
  })

  it('没有 run_end 的一轮标记为运行中', () => {
    const turns = splitTurns([
      entry('run_start', { task: '正在跑' }),
      entry('tool_call', { action: 'run_tests', observation: '...' }),
    ])
    expect(turns[0]?.running).toBe(true)
    expect(turns[0]?.answer).toBe('')
    expect(turns[0]?.status).toBe('')
  })

  it('统计执行过程但不把 message 算进去', () => {
    // message 是对话历史的原始载体，在对话视图里由 run_start / run_end 表达。
    const turns = splitTurns(
      turnEntries('问', '答', [
        entry('message', { role: 'user', content: '问' }),
        entry('replan', { reason: 'tool_failure' }),
      ]),
    )
    const turn = turns[0]
    expect(turn?.stepCount).toBe(1)
    expect(turn?.toolCallCount).toBe(1)
    expect(turn?.replanCount).toBe(1)
    expect(turn?.activity.some((item) => item.event === 'message')).toBe(false)
    // 但原文仍在这一轮的 entries 里——审计抽屉要能看到。
    expect(turn?.entries.some((item) => item.event === 'message')).toBe(true)
  })

  it('把失败标出来，收起状态下也看得见这轮不顺', () => {
    const turns = splitTurns(
      turnEntries('问', '答', [
        entry('tool_call', { action: 'read_file', failed: true, observation: '不存在' }),
      ]),
    )
    expect(turns[0]?.failed).toBe(true)
  })

  it('顺利的一轮不会被误标为失败', () => {
    expect(splitTurns(turnEntries('问', '答'))[0]?.failed).toBe(false)
  })

  it('空日志得到空数组而不是抛错', () => {
    expect(splitTurns([])).toEqual([])
  })
})

describe('describeActivity', () => {
  it('拼出人话摘要', () => {
    const turn = splitTurns(turnEntries('问', '答', [entry('replan', { reason: 'x' })]))[0]!
    expect(describeActivity(turn)).toBe('1 步 · 1 次工具调用 · 1 次重规划')
  })

  it('没有可数动作时退回条目数', () => {
    const turn = splitTurns([
      entry('run_start', { task: '问' }),
      entry('compaction', { estimated_tokens_before: 100, estimated_tokens_after: 60 }),
    ])[0]!
    expect(describeActivity(turn)).toBe('1 条记录')
  })

  it('完全没有过程时是空串', () => {
    const turn = splitTurns([entry('run_start', { task: '问' })])[0]!
    expect(describeActivity(turn)).toBe('')
  })
})

describe('describeActivityEntry', () => {
  it('折叠明确写出「原文仍在」', () => {
    const text = describeActivityEntry(
      entry('compaction', { estimated_tokens_before: 900, estimated_tokens_after: 400 }),
    )
    expect(text).toBe('上下文折叠 900 → 400 tokens（原文仍在）')
  })

  it('工具调用显示观察结果', () => {
    expect(describeActivityEntry(entry('tool_call', { observation: '3 passed' }))).toBe('3 passed')
  })

  it('计划显示步数', () => {
    expect(describeActivityEntry(entry('plan', { steps: [{}, {}, {}] }))).toBe('生成了 3 步计划')
  })

  it('未知事件退回错误或观察字段，不猜', () => {
    expect(describeActivityEntry(entry('weird_event', { error: '炸了' }))).toBe('炸了')
    expect(describeActivityEntry(entry('weird_event', {}))).toBe('')
  })
})

describe('labelActivityEntry', () => {
  it('优先显示动作名', () => {
    expect(labelActivityEntry(entry('tool_call', { action: 'run_tests' }))).toBe('run_tests')
  })

  it('没有动作名时退回事件名', () => {
    expect(labelActivityEntry(entry('compaction', {}))).toBe('compaction')
  })
})

describe('looksLikeConversation', () => {
  it('有 run_start 才能当对话读', () => {
    expect(looksLikeConversation(turnEntries('问', '答'))).toBe(true)
  })

  it('只含 checkpoint 条目的文件退回执行链视图', () => {
    expect(looksLikeConversation([entry('checkpoint', { step_number: 1 })])).toBe(false)
  })
})
