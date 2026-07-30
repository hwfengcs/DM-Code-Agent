/** 全站共用的展示原语。颜色只编码语义，不做装饰。 */
import { useState, type ReactNode } from 'react'
import type { TraceHealth } from '../lib/types'
import { describeIssue } from '../lib/entries'

const GRADE_STYLE: Record<string, string> = {
  good: 'border-signal-good/40 bg-signal-good/10 text-signal-good',
  warning: 'border-signal-warn/40 bg-signal-warn/10 text-signal-warn',
  risky: 'border-signal-risk/40 bg-signal-risk/10 text-signal-risk',
}

const GRADE_LABEL: Record<string, string> = {
  good: '健康',
  warning: '需注意',
  risky: '有风险',
}

export function HealthBadge({ health, showScore = true }: { health: TraceHealth; showScore?: boolean }) {
  const style = GRADE_STYLE[health.grade] ?? GRADE_STYLE.warning
  return (
    <span
      className={`chip ${style}`}
      title={health.issues.map(describeIssue).join('\n') || '没有发现问题'}
    >
      <span className="inline-block size-1.5 rounded-full bg-current" />
      {GRADE_LABEL[health.grade] ?? health.grade}
      {showScore && <span className="opacity-60">{health.score.toFixed(2)}</span>}
    </span>
  )
}

/**
 * 运行状态。
 *
 * `success` / `completed` 用中性色而不是绿色——**「成功」本身不代表过程健康**，
 * 绿色留给 HealthBadge。`incomplete`（退出码 0 但 agent 没宣布完成，如步数耗尽）
 * 必须显眼，否则它看起来会跟成功一样。
 */
export function StatusChip({ status }: { status: string }) {
  const style =
    status === 'success' || status === 'completed'
      ? 'border-scope-line bg-scope-raised text-scope-text'
      : status === 'running'
        ? 'border-signal-info/40 bg-signal-info/10 text-signal-info'
        : status === 'max_steps_exceeded' || status === 'incomplete' || status === 'cancelled'
          ? 'border-signal-warn/40 bg-signal-warn/10 text-signal-warn'
          : status
            ? 'border-signal-risk/40 bg-signal-risk/10 text-signal-risk'
            : 'border-scope-line bg-scope-raised text-scope-faint'
  return <span className={`chip ${style}`}>{STATUS_LABEL[status] ?? status ?? '未完成'}</span>
}

const STATUS_LABEL: Record<string, string> = {
  running: '运行中',
  completed: '已完成',
  incomplete: '未做完',
  failed: '失败',
  cancelled: '已取消',
}

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className = '',
  bodyClassName = '',
}: {
  title?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}) {
  return (
    <section className={`panel flex min-h-0 flex-col ${className}`}>
      {(title || actions) && (
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-scope-line-soft px-3 py-2">
          <div className="min-w-0">
            {title && <h2 className="meta-label truncate">{title}</h2>}
            {subtitle && <p className="truncate text-xs text-scope-dim">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-1">{actions}</div>}
        </header>
      )}
      <div className={`min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  )
}

export function MetaRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-baseline gap-3 py-0.5">
      <span className="meta-label w-28 shrink-0">{label}</span>
      <span className="min-w-0 flex-1 truncate font-mono text-xs text-scope-text">{value}</span>
    </div>
  )
}

export function Spinner({ label = '读取中' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 p-6 font-mono text-xs text-scope-dim">
      <span className="inline-block size-2 animate-ping rounded-full bg-signal-info" />
      {label}…
    </div>
  )
}

export function ErrorBox({ title, detail, action }: { title: string; detail?: string; action?: ReactNode }) {
  return (
    <div className="m-4 rounded-lg border border-signal-risk/40 bg-signal-risk/5 p-4">
      <p className="font-mono text-sm text-signal-risk">{title}</p>
      {detail && <p className="mt-1 font-mono text-xs break-words text-scope-dim">{detail}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}

export function EmptyState({ title, hint }: { title: string; hint?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 p-10 text-center">
      <p className="font-mono text-sm text-scope-dim">{title}</p>
      {hint && <p className="max-w-md text-xs text-scope-faint">{hint}</p>}
    </div>
  )
}

export function Button({
  children,
  onClick,
  variant = 'ghost',
  disabled = false,
  title,
}: {
  children: ReactNode
  onClick?: () => void
  variant?: 'ghost' | 'primary' | 'danger'
  disabled?: boolean
  title?: string
}) {
  const style =
    variant === 'primary'
      ? 'border-signal-info/50 bg-signal-info/10 text-signal-info hover:bg-signal-info/20'
      : variant === 'danger'
        ? 'border-signal-risk/50 bg-signal-risk/10 text-signal-risk hover:bg-signal-risk/20'
        : 'border-scope-line bg-scope-raised text-scope-dim hover:border-scope-faint hover:text-scope-text'
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`focus-ring rounded border px-2 py-1 font-mono text-[11px] transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${style}`}
    >
      {children}
    </button>
  )
}

/**
 * payload 渲染器。
 *
 * 长字符串（观察结果、原始响应）默认折起来——审计时你想先看结构，
 * 需要时再逐字展开，而不是被一屏 8000 字的观察淹掉。
 */
export function JsonView({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value === null) return <span className="text-scope-faint">null</span>
  if (typeof value === 'boolean')
    return <span className={value ? 'text-signal-good' : 'text-signal-warn'}>{String(value)}</span>
  if (typeof value === 'number') return <span className="text-signal-info">{value}</span>
  if (typeof value === 'string') return <LongText text={value} />

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-scope-faint">[]</span>
    return (
      <ul className="space-y-0.5">
        {value.map((item, index) => (
          <li key={index} className="flex gap-2">
            <span className="shrink-0 text-scope-faint">{index}</span>
            <div className="min-w-0 flex-1">
              <JsonView value={item} depth={depth + 1} />
            </div>
          </li>
        ))}
      </ul>
    )
  }

  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
    if (entries.length === 0) return <span className="text-scope-faint">{'{}'}</span>
    return (
      <dl className="space-y-0.5">
        {entries.map(([key, item]) => (
          <div key={key} className="flex gap-2">
            <dt className="shrink-0 text-scope-dim">{key}</dt>
            <dd className="min-w-0 flex-1">
              <JsonView value={item} depth={depth + 1} />
            </dd>
          </div>
        ))}
      </dl>
    )
  }
  return <span className="text-scope-faint">{String(value)}</span>
}

const LONG_TEXT_THRESHOLD = 280

function LongText({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false)
  if (text.length <= LONG_TEXT_THRESHOLD) {
    return <span className="break-words whitespace-pre-wrap text-scope-text">{text}</span>
  }
  return (
    <div>
      <span className="break-words whitespace-pre-wrap text-scope-text">
        {expanded ? text : `${text.slice(0, LONG_TEXT_THRESHOLD)}…`}
      </span>
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="focus-ring ml-2 rounded text-[11px] text-signal-info hover:underline"
      >
        {expanded ? '收起' : `展开全部 ${text.length} 字`}
      </button>
    </div>
  )
}
