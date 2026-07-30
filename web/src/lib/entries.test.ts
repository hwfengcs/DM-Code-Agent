/**
 * 展示层纯函数的单测。
 *
 * 这里**不测**任何诊断结论——那些是后端 `dm_agent.tracing` 的职责，
 * 由 `tests/test_server_readonly.py` 覆盖。这里只测分组、归类、树还原、格式化。
 */
import { describe, expect, it } from 'vitest'
import {
  buildTree,
  classifyEvent,
  compactionSpans,
  describeIssue,
  foldedEntryIds,
  formatBytes,
  formatDuration,
  formatRelative,
  groupByStep,
  isFailureEntry,
  splitRuns,
} from './entries'
import type { SessionEntry } from './types'

function entry(
  id: string,
  event: string,
  payload: Record<string, unknown> = {},
  parent = '',
): SessionEntry {
  return {
    id,
    parent_id: parent,
    timestamp: '2026-02-01T00:00:00+00:00',
    run_id: 'run-1',
    event,
    payload,
  }
}

/** 把一串条目按顺序连成父子链，模拟真实会话日志。 */
function chain(items: [string, string, Record<string, unknown>?][]): SessionEntry[] {
  let parent = ''
  return items.map(([id, event, payload]) => {
    const made = entry(id, event, payload ?? {}, parent)
    parent = id
    return made
  })
}

describe('classifyEvent', () => {
  it('把成功与失败的 tool_call 分到不同类别', () => {
    expect(classifyEvent(entry('a', 'tool_call', { failed: false }))).toBe('tool')
    expect(classifyEvent(entry('a', 'tool_call', { failed: true }))).toBe('failure')
  })

  it('识别生命周期、计划与折叠事件', () => {
    expect(classifyEvent(entry('a', 'run_start'))).toBe('lifecycle')
    expect(classifyEvent(entry('a', 'run_end'))).toBe('lifecycle')
    expect(classifyEvent(entry('a', 'fork'))).toBe('lifecycle')
    expect(classifyEvent(entry('a', 'plan'))).toBe('plan')
    expect(classifyEvent(entry('a', 'compaction'))).toBe('compaction')
    expect(classifyEvent(entry('a', 'replan'))).toBe('replan')
  })

  it('把各类 *_error 归到失败', () => {
    expect(classifyEvent(entry('a', 'parse_error'))).toBe('failure')
    expect(classifyEvent(entry('a', 'llm_error'))).toBe('failure')
    expect(classifyEvent(entry('a', 'run_error'))).toBe('failure')
  })

  it('没见过的事件归到 other，而不是猜', () => {
    expect(classifyEvent(entry('a', 'some_future_event'))).toBe('other')
  })
})

describe('isFailureEntry', () => {
  it('critic 未通过算失败，通过不算', () => {
    expect(isFailureEntry(entry('a', 'critic_review', { passed: false }))).toBe(true)
    expect(isFailureEntry(entry('a', 'critic_review', { passed: true }))).toBe(false)
  })

  it('缺少 failed 字段的 tool_call 不算失败', () => {
    expect(isFailureEntry(entry('a', 'tool_call', {}))).toBe(false)
  })
})

describe('groupByStep', () => {
  it('按步骤号聚合，并把运行级条目单独成组', () => {
    const groups = groupByStep(
      chain([
        ['e1', 'run_start'],
        ['e2', 'plan'],
        ['e3', 'llm_call', { step_number: 1 }],
        ['e4', 'tool_call', { step_number: 1, action: 'read_file', failed: true }],
        ['e5', 'step', { step_number: 1, action: 'read_file' }],
        ['e6', 'step', { step_number: 2, action: 'create_file' }],
        ['e7', 'run_end'],
      ]),
    )
    expect(groups.map((group) => group.stepNumber)).toEqual([null, 1, 2, null])
    expect(groups[1]?.action).toBe('read_file')
    expect(groups[1]?.failed).toBe(true)
    expect(groups[2]?.failed).toBe(false)
    expect(groups[1]?.entries).toHaveLength(3)
  })

  it('同一步骤号被中断后重新出现时会分成两组，保持时间顺序', () => {
    const groups = groupByStep(
      chain([
        ['e1', 'step', { step_number: 1 }],
        ['e2', 'step', { step_number: 2 }],
        ['e3', 'step', { step_number: 1 }],
      ]),
    )
    expect(groups.map((group) => group.stepNumber)).toEqual([1, 2, 1])
  })

  it('空输入返回空数组', () => {
    expect(groupByStep([])).toEqual([])
  })
})

describe('splitRuns', () => {
  it('一份日志里的多段 run 会被切开，首段包含 run_start 之前的条目', () => {
    const entries = chain([
      ['e1', 'runtime'],
      ['e2', 'run_start', { task: '第一段' }],
      ['e3', 'run_end'],
      ['e4', 'run_start', { task: '第二段' }],
      ['e5', 'run_end'],
    ])
    const runs = splitRuns(entries)
    expect(runs).toHaveLength(2)
    expect(runs[0]).toMatchObject({ startIndex: 0, endIndex: 2, task: '第一段' })
    expect(runs[1]).toMatchObject({ startIndex: 3, endIndex: 4, task: '第二段' })
  })

  it('没有 run_start 时退化成单段', () => {
    expect(splitRuns(chain([['e1', 'step']]))).toHaveLength(1)
    expect(splitRuns([])).toEqual([])
  })
})

describe('compactionSpans 与 foldedEntryIds', () => {
  const entries = chain([
    ['m1', 'message', { role: 'user', content: '第一条' }],
    ['m2', 'message', { role: 'assistant', content_chars: 120 }],
    ['m3', 'message', { role: 'user', content: '第三条' }],
    [
      'c1',
      'compaction',
      {
        folded_entry_ids: ['m1', 'm2'],
        first_kept_entry_id: 'm3',
        estimated_tokens_before: 900,
        estimated_tokens_after: 400,
        phase: 'commit',
        trigger: 'token_budget',
      },
    ],
  ])

  it('抽取折叠的收益与边界', () => {
    const spans = compactionSpans(entries)
    expect(spans).toHaveLength(1)
    expect(spans[0]).toMatchObject({
      foldedIds: ['m1', 'm2'],
      firstKeptId: 'm3',
      tokensBefore: 900,
      tokensAfter: 400,
      phase: 'commit',
      trigger: 'token_budget',
    })
  })

  it('被折叠的原文条目仍在列表里——折叠只追加，不删除', () => {
    const folded = foldedEntryIds(entries)
    expect(folded).toEqual(new Set(['m1', 'm2']))
    // 关键断言：原始 message 条目一条都没少。
    expect(entries.filter((item) => item.event === 'message')).toHaveLength(3)
  })

  it('字段缺失时降级为 null，不抛异常', () => {
    const spans = compactionSpans(chain([['c1', 'compaction', {}]]))
    expect(spans[0]).toMatchObject({ foldedIds: [], tokensBefore: null, tokensAfter: null })
  })
})

describe('buildTree', () => {
  it('把线性会话还原成一条链', () => {
    const roots = buildTree(
      chain([
        ['e1', 'run_start'],
        ['e2', 'step'],
        ['e3', 'run_end'],
      ]),
    )
    expect(roots).toHaveLength(1)
    expect(roots[0]?.children[0]?.entry.id).toBe('e2')
    expect(roots[0]?.children[0]?.children[0]?.depth).toBe(2)
  })

  it('parent 不在本文件里的条目自成新根（分叉会话的情形）', () => {
    const roots = buildTree([
      entry('f1', 'fork', {}, 'source-0007'),
      entry('f2', 'step', {}, 'f1'),
    ])
    expect(roots).toHaveLength(1)
    expect(roots[0]?.entry.id).toBe('f1')
    expect(roots[0]?.children).toHaveLength(1)
  })
})

describe('格式化', () => {
  it('formatDuration 按量级切换单位', () => {
    expect(formatDuration(null)).toBe('—')
    expect(formatDuration(0.25)).toBe('250ms')
    expect(formatDuration(1.25)).toBe('1.3s')
    expect(formatDuration(125)).toBe('2m5s')
  })

  it('formatBytes 按量级切换单位', () => {
    expect(formatBytes(512)).toBe('512B')
    expect(formatBytes(2048)).toBe('2.0KB')
    expect(formatBytes(5 * 1024 * 1024)).toBe('5.0MB')
  })

  it('formatRelative 用固定的 now 保证可测', () => {
    const now = 1_800_000_000_000
    expect(formatRelative(now / 1000 - 30, now)).toBe('刚刚')
    expect(formatRelative(now / 1000 - 120, now)).toBe('2 分钟前')
    expect(formatRelative(now / 1000 - 7200, now)).toBe('2 小时前')
    expect(formatRelative(now / 1000 - 86400 * 3, now)).toBe('3 天前')
  })

  it('describeIssue 翻译已知信号，未知的原样返回', () => {
    expect(describeIssue('verification_gap')).toBe('宣布完成前没跑过任何验证')
    expect(describeIssue('final_failure:tool')).toBe('最终失败在 tool 阶段')
    expect(describeIssue('brand_new_signal')).toBe('brand_new_signal')
  })
})
