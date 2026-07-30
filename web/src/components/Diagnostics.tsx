/**
 * 诊断面板：把 `analyze_events` 的结论渲染成人能扫一眼的卡片。
 *
 * 这个面板存在的理由就一句话：**任务成功 ≠ 过程健康**，而后者是能被机器读出来的。
 * 所以「验证缺口」那张卡在成功的运行上也要显眼。
 */
import type { SessionAnalysis } from '../lib/types'
import { describeIssue } from '../lib/entries'
import { HealthBadge } from './ui'

export function Diagnostics({ analysis }: { analysis: SessionAnalysis }) {
  const { recovery, verification, trace_health: health } = analysis

  return (
    <div className="space-y-3 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <HealthBadge health={health} />
        {analysis.signals.length === 0 && (
          <span className="font-mono text-xs text-scope-dim">没有触发任何诊断信号</span>
        )}
        {analysis.signals.map((signal) => (
          <span key={signal} className="chip border-scope-line bg-scope-raised text-scope-dim">
            {describeIssue(signal)}
          </span>
        ))}
      </div>

      <Card
        tone={verification.gap ? 'warn' : 'good'}
        title="验证"
        headline={
          verification.gap
            ? '宣布完成前没跑过任何验证'
            : verification.before_finish
              ? '完成前跑过验证'
              : '本次运行没有完成'
        }
      >
        <Line label="验证动作" value={`${verification.count} 次`} />
        <Line
          label="完成步骤"
          value={verification.finish_step === null ? '未完成' : `第 ${verification.finish_step} 步`}
        />
        {verification.actions.length > 0 && (
          <Line
            label="具体动作"
            value={verification.actions
              .map((action) => `#${action.step_number} ${action.action}`)
              .join('、')}
          />
        )}
        {verification.gap && (
          <p className="mt-2 text-[11px] text-scope-faint">
            运行成功但全程没有执行 run_tests / run_linter 一类的验证动作。结果可能是对的，
            但这次运行本身没有给出任何证据。
          </p>
        )}
      </Card>

      <Card
        tone={recovery.failure_event_count === 0 ? 'good' : recovery.recovered ? 'info' : 'risk'}
        title="失败与恢复"
        headline={
          recovery.failure_event_count === 0
            ? '全程无失败'
            : recovery.recovered
              ? `出现 ${recovery.failure_event_count} 次失败，最终恢复`
              : `出现 ${recovery.failure_event_count} 次失败，未恢复`
        }
      >
        <Line label="首次失败阶段" value={analysis.primary_failure_stage} />
        <Line label="最终失败阶段" value={analysis.final_failure_stage} />
        <Line
          label="首次失败位置"
          value={
            recovery.first_failure_step === null
              ? '—'
              : `第 ${recovery.first_failure_step} 步（${recovery.first_failure_event ?? '?'}）`
          }
        />
        <Line label="重规划次数" value={String(recovery.replan_count)} />
        <Line
          label="失败后是否重规划"
          value={recovery.replanned_after_failure ? '是' : '否'}
          tone={recovery.failure_event_count > 0 && !recovery.replanned_after_failure ? 'warn' : undefined}
        />
      </Card>

      <Card
        tone={hasAnySignal(analysis.hallucination_signals) ? 'warn' : 'good'}
        title="幻觉信号"
        headline={
          hasAnySignal(analysis.hallucination_signals)
            ? '检测到可疑行为'
            : '未检测到可疑行为'
        }
      >
        {Object.entries(analysis.hallucination_signals).map(([key, value]) => (
          <Line
            key={key}
            label={HALLUCINATION_LABEL[key] ?? key}
            value={String(value)}
            tone={typeof value === 'number' && value > 0 ? 'warn' : undefined}
          />
        ))}
      </Card>

      {Object.keys(analysis.metadata_counters).length > 0 && (
        <Card tone="neutral" title="计数器" headline="运行期累计的错误与重规划计数">
          {Object.entries(analysis.metadata_counters).map(([key, value]) => (
            <Line key={key} label={key} value={String(value)} />
          ))}
        </Card>
      )}

      {health.issues.length > 0 && (
        <Card tone="warn" title="健康度扣分项" headline={`共 ${health.issues.length} 项`}>
          <ul className="space-y-1">
            {health.issues.map((issue) => (
              <li key={issue} className="font-mono text-[11px] text-scope-dim">
                · {describeIssue(issue)}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}

const HALLUCINATION_LABEL: Record<string, string> = {
  edit_without_read: '未读先改',
  guard_blocks: '被守卫拦下',
  truncations: '观察被截断',
  missing_paths: '引用了不存在的路径',
}

function hasAnySignal(signals: Record<string, number>): boolean {
  return Object.values(signals).some((value) => typeof value === 'number' && value > 0)
}

const TONE_STYLE = {
  good: 'border-signal-good/30',
  warn: 'border-signal-warn/40',
  risk: 'border-signal-risk/40',
  info: 'border-signal-info/30',
  neutral: 'border-scope-line',
} as const

const TONE_TEXT = {
  good: 'text-signal-good',
  warn: 'text-signal-warn',
  risk: 'text-signal-risk',
  info: 'text-signal-info',
  neutral: 'text-scope-text',
} as const

function Card({
  title,
  headline,
  tone,
  children,
}: {
  title: string
  headline: string
  tone: keyof typeof TONE_STYLE
  children: React.ReactNode
}) {
  return (
    <section className={`rounded-lg border bg-scope-panel ${TONE_STYLE[tone]}`}>
      <header className="border-b border-scope-line-soft px-3 py-2">
        <div className="meta-label">{title}</div>
        <div className={`text-sm ${TONE_TEXT[tone]}`}>{headline}</div>
      </header>
      <div className="px-3 py-2">{children}</div>
    </section>
  )
}

function Line({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone?: 'warn'
}) {
  return (
    <div className="flex items-baseline gap-3 py-0.5">
      <span className="meta-label w-32 shrink-0">{label}</span>
      <span
        className={`min-w-0 flex-1 font-mono text-xs ${tone === 'warn' ? 'text-signal-warn' : 'text-scope-text'}`}
      >
        {value}
      </span>
    </div>
  )
}
