/**
 * 诊断面板：把 `analyze_events` 的结论渲染成人能扫一眼的卡片。
 *
 * 这个面板存在的理由就一句话：**任务成功 ≠ 过程健康**，而后者是能被机器读出来的。
 * 所以「验证缺口」那张卡在成功的运行上也要显眼。
 *
 * 前端不重算任何结论——全部来自后端 `dm_agent.tracing.analysis`，这里只负责渲染。
 */
import type { SessionAnalysis } from '../lib/types'
import { describeIssue } from '../lib/entries'
import { HealthBadge, HealthDetail } from './ui'

export function Diagnostics({ analysis }: { analysis: SessionAnalysis }) {
  const { recovery, verification, trace_health: health } = analysis

  return (
    <div className="space-y-4 p-5">
      {/* 健康度总览。扣分项直接平铺，不藏在 tooltip 里。 */}
      <section className="card p-5">
        <div className="flex flex-wrap items-center gap-3">
          <HealthBadge health={health} />
          <span className="text-caption text-ink-2">
            评分 <span className="font-mono tabular-nums text-ink">{health.score.toFixed(2)}</span>
          </span>
        </div>
        <div className="mt-3 border-t border-line pt-3">
          <HealthDetail health={health} />
        </div>
        {analysis.signals.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5 border-t border-line pt-3">
            {analysis.signals.map((signal) => (
              <span key={signal} className="chip border-line-strong bg-muted text-ink-2">
                {describeIssue(signal)}
              </span>
            ))}
          </div>
        )}
      </section>

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
          <p className="mt-3 border-t border-line pt-3 text-micro text-ink-2">
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
          tone={
            recovery.failure_event_count > 0 && !recovery.replanned_after_failure
              ? 'warn'
              : undefined
          }
        />
      </Card>

      <Card
        tone={hasAnySignal(analysis.hallucination_signals) ? 'warn' : 'good'}
        title="幻觉信号"
        headline={
          hasAnySignal(analysis.hallucination_signals) ? '检测到可疑行为' : '未检测到可疑行为'
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
            <Line key={key} label={key} value={String(value)} mono />
          ))}
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

const TONE_DOT = {
  good: 'bg-green',
  warn: 'bg-orange',
  risk: 'bg-red',
  info: 'bg-blue',
  neutral: 'bg-ink-4',
} as const

const TONE_TEXT = {
  good: 'text-green-ink',
  warn: 'text-orange-ink',
  risk: 'text-red-ink',
  info: 'text-blue-ink',
  neutral: 'text-ink',
} as const

function Card({
  title,
  headline,
  tone,
  children,
}: {
  title: string
  headline: string
  tone: keyof typeof TONE_DOT
  children: React.ReactNode
}) {
  return (
    <section className="card">
      <header className="border-b border-line px-5 py-3.5">
        <div className="text-micro font-medium text-ink-3">{title}</div>
        <div className="mt-0.5 flex items-center gap-2">
          <span className={`inline-block size-2 shrink-0 rounded-full ${TONE_DOT[tone]}`} />
          <span className={`text-body font-semibold ${TONE_TEXT[tone]}`}>{headline}</span>
        </div>
      </header>
      <div className="px-5 py-3.5">{children}</div>
    </section>
  )
}

function Line({
  label,
  value,
  tone,
  mono = false,
}: {
  label: string
  value: string
  tone?: 'warn'
  mono?: boolean
}) {
  return (
    <div className="flex items-baseline gap-4 py-1">
      <span className={`w-36 shrink-0 text-micro text-ink-3 ${mono ? 'font-mono' : ''}`}>
        {label}
      </span>
      <span
        className={`min-w-0 flex-1 text-caption ${
          tone === 'warn' ? 'font-medium text-orange-ink' : 'text-ink'
        }`}
      >
        {value}
      </span>
    </div>
  )
}
