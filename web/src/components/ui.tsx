/**
 * 全站共用的展示原语。
 *
 * 两条规则：
 *   1. 颜色只编码语义，不做装饰；白底上的语义**文字**用 `-ink` 加深变体，
 *      饱和原色只用于填充、边框和圆点（对比度理由见 index.css）。
 *   2. `font-mono` 只出现在证据上（id、路径、payload、token 数），UI 语言一律 sans。
 */
import { useState, type ReactNode } from 'react'
import type { TraceHealth } from '../lib/types'
import { describeIssue } from '../lib/entries'

const GRADE_CHIP: Record<string, string> = {
  good: 'border-green/25 bg-green/10 text-green-ink',
  warning: 'border-orange/25 bg-orange/10 text-orange-ink',
  risky: 'border-red/25 bg-red/10 text-red-ink',
}

const GRADE_DOT: Record<string, string> = {
  good: 'bg-green',
  warning: 'bg-orange',
  risky: 'bg-red',
}

const GRADE_LABEL: Record<string, string> = {
  good: '健康',
  warning: '需注意',
  risky: '有风险',
}

export function HealthBadge({
  health,
  showScore = true,
}: {
  health: TraceHealth
  showScore?: boolean
}) {
  return (
    <span className={`chip ${GRADE_CHIP[health.grade] ?? GRADE_CHIP.warning}`}>
      <span className={`inline-block size-1.5 rounded-full ${GRADE_DOT[health.grade] ?? 'bg-orange'}`} />
      {GRADE_LABEL[health.grade] ?? health.grade}
      {showScore && <span className="tabular-nums opacity-55">{health.score.toFixed(2)}</span>}
    </span>
  )
}

/**
 * 健康度扣分项**明细**。
 *
 * 上一版把 issues 塞在徽章的 HTML `title` 属性里，必须鼠标悬停才看得见——对一个
 * 主打可审计的产品这是硬伤。这里改成直接平铺，不需要任何交互就能读到全部结论。
 */
export function HealthDetail({ health }: { health: TraceHealth }) {
  if (health.issues.length === 0) {
    return (
      <p className="flex items-center gap-2 text-caption text-ink-2">
        <span className="inline-block size-1.5 rounded-full bg-green" />
        没有发现扣分项
      </p>
    )
  }
  return (
    <ul className="space-y-1.5">
      {health.issues.map((issue) => (
        <li key={issue} className="flex items-start gap-2 text-caption text-ink-2">
          <span className="mt-1.5 inline-block size-1.5 shrink-0 rounded-full bg-orange" />
          {describeIssue(issue)}
        </li>
      ))}
    </ul>
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
      ? 'border-line-strong bg-muted text-ink-2'
      : status === 'running'
        ? 'border-blue/25 bg-blue/10 text-blue-ink'
        : status === 'max_steps_exceeded' || status === 'incomplete' || status === 'cancelled'
          ? 'border-orange/25 bg-orange/10 text-orange-ink'
          : status
            ? 'border-red/25 bg-red/10 text-red-ink'
            : 'border-line-strong bg-muted text-ink-3'
  return <span className={`chip ${style}`}>{STATUS_LABEL[status] ?? status ?? '未完成'}</span>
}

const STATUS_LABEL: Record<string, string> = {
  running: '运行中',
  completed: '已完成',
  success: '已完成',
  incomplete: '未做完',
  failed: '失败',
  cancelled: '已取消',
  max_steps_exceeded: '步数耗尽',
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
    <section className={`card flex min-h-0 flex-col ${className}`}>
      {(title || actions) && (
        <header className="flex shrink-0 items-center justify-between gap-4 border-b border-line px-5 py-3.5">
          <div className="min-w-0">
            {title && <h2 className="truncate text-caption font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 truncate text-micro text-ink-3">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={`min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  )
}

/** 统计卡。`emphasis` 那张用大字号与语义色，用于「成功但不健康」这类要被看见的数字。 */
export function Stat({
  label,
  value,
  hint,
  tone = 'neutral',
  emphasis = false,
}: {
  label: string
  value: string
  hint?: string
  tone?: 'neutral' | 'good' | 'warn' | 'risk'
  emphasis?: boolean
}) {
  const color =
    tone === 'good'
      ? 'text-green-ink'
      : tone === 'warn'
        ? 'text-orange-ink'
        : tone === 'risk'
          ? 'text-red-ink'
          : 'text-ink'
  return (
    <div className={`card px-5 py-4 ${emphasis ? 'ring-1 ring-orange/20' : ''}`}>
      <div className="text-micro font-medium text-ink-2">{label}</div>
      <div className={`mt-1 tabular-nums ${emphasis ? 'text-display' : 'text-title'} font-semibold ${color}`}>
        {value}
      </div>
      {hint && <div className="mt-0.5 text-micro text-ink-3">{hint}</div>}
    </div>
  )
}

/** 元信息行：左侧固定宽度标签 + 右侧证据值。 */
export function MetaRow({
  label,
  value,
  mono = true,
}: {
  label: string
  value: ReactNode
  mono?: boolean
}) {
  return (
    <div className="flex items-baseline gap-4 py-1">
      <span className="w-24 shrink-0 text-micro text-ink-3">{label}</span>
      <span className={`min-w-0 flex-1 truncate text-caption text-ink ${mono ? 'font-mono' : ''}`}>
        {value}
      </span>
    </div>
  )
}

/** 审计横幅。用于把「成功但没验证」这类结论顶到首屏，而不是埋在二级 tab 里。 */
export function Banner({
  tone,
  title,
  children,
  action,
}: {
  tone: 'warn' | 'risk' | 'info'
  title: string
  children?: ReactNode
  action?: ReactNode
}) {
  const style =
    tone === 'risk'
      ? 'border-red/25 bg-red/[0.06]'
      : tone === 'warn'
        ? 'border-orange/25 bg-orange/[0.06]'
        : 'border-blue/25 bg-blue/[0.06]'
  const dot = tone === 'risk' ? 'bg-red' : tone === 'warn' ? 'bg-orange' : 'bg-blue'
  const head = tone === 'risk' ? 'text-red-ink' : tone === 'warn' ? 'text-orange-ink' : 'text-blue-ink'
  return (
    <div className={`flex items-start gap-3 rounded-card border px-4 py-3 ${style}`}>
      <span className={`mt-1.5 inline-block size-2 shrink-0 rounded-full ${dot}`} />
      <div className="min-w-0 flex-1">
        <p className={`text-caption font-semibold ${head}`}>{title}</p>
        {children && <div className="mt-1 text-micro text-ink-2">{children}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T
  options: { value: T; label: string }[]
  onChange: (value: T) => void
}) {
  return (
    <div className="segmented" role="tablist">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="tab"
          aria-selected={value === option.value}
          data-active={value === option.value}
          onClick={() => onChange(option.value)}
          className="segmented-item focus-ring"
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

/**
 * 页面标题栏。侧栏承担全局导航后，顶栏瘦身成「这一页是什么 + 这一页能做什么」。
 *
 * 放在 ui.tsx 而不是 App.tsx，是为了避免 App → views → App 的循环 import。
 */
export function PageHeader({
  title,
  description,
  back,
  actions,
  children,
}: {
  title: ReactNode
  description?: ReactNode
  back?: { href: string; label: string }
  actions?: ReactNode
  children?: ReactNode
}) {
  return (
    <header className="shrink-0 border-b border-line bg-canvas px-8 pt-6 pb-5">
      {back && (
        <a
          href={back.href}
          className="focus-ring mb-2 inline-flex items-center gap-1 rounded text-micro font-medium text-ink-2 hover:text-blue"
        >
          <span aria-hidden="true">←</span>
          {back.label}
        </a>
      )}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="truncate text-title font-semibold text-ink">{title}</h1>
          {description && <div className="mt-1 text-caption text-ink-2">{description}</div>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </header>
  )
}

export function Spinner({ label = '读取中' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2.5 p-8 text-caption text-ink-2">
      <span className="inline-block size-3.5 animate-spin rounded-full border-2 border-line-strong border-t-blue" />
      {label}…
    </div>
  )
}

export function ErrorBox({
  title,
  detail,
  action,
}: {
  title: string
  detail?: string
  action?: ReactNode
}) {
  return (
    <div className="m-8 rounded-card border border-red/25 bg-red/[0.06] p-5">
      <p className="text-heading font-semibold text-red-ink">{title}</p>
      {detail && <p className="mt-1.5 font-mono text-caption break-words text-ink-2">{detail}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function EmptyState({ title, hint }: { title: string; hint?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-16 text-center">
      <p className="text-body font-medium text-ink-2">{title}</p>
      {hint && <p className="max-w-md text-caption text-ink-3">{hint}</p>}
    </div>
  )
}

export function Button({
  children,
  onClick,
  variant = 'secondary',
  size = 'md',
  disabled = false,
  title,
  type = 'button',
}: {
  children: ReactNode
  onClick?: () => void
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md'
  disabled?: boolean
  title?: string
  type?: 'button' | 'submit'
}) {
  const style =
    variant === 'primary'
      ? 'border-transparent bg-blue text-white hover:bg-blue-ink'
      : variant === 'danger'
        ? 'border-red/30 bg-red/10 text-red-ink hover:bg-red/15'
        : variant === 'ghost'
          ? 'border-transparent bg-transparent text-ink-2 hover:bg-muted hover:text-ink'
          : 'border-line-strong bg-surface text-ink hover:border-ink-4 hover:bg-muted'
  const sizing = size === 'sm' ? 'px-2.5 py-1 text-micro' : 'px-3.5 py-1.5 text-caption'
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`focus-ring rounded-control border font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${sizing} ${style}`}
    >
      {children}
    </button>
  )
}

/** 内联链接按钮。用于「跳到诊断」这类页内导航。 */
export function LinkButton({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="focus-ring rounded text-caption font-medium text-blue hover:underline"
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
  if (value === null) return <span className="text-ink-4">null</span>
  if (typeof value === 'boolean')
    return <span className={value ? 'text-green-ink' : 'text-orange-ink'}>{String(value)}</span>
  if (typeof value === 'number') return <span className="text-blue-ink tabular-nums">{value}</span>
  if (typeof value === 'string') return <LongText text={value} />

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-ink-4">[]</span>
    return (
      <ul className="space-y-1">
        {value.map((item, index) => (
          <li key={index} className="flex gap-2.5">
            <span className="shrink-0 tabular-nums text-ink-4">{index}</span>
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
    if (entries.length === 0) return <span className="text-ink-4">{'{}'}</span>
    return (
      <dl className="space-y-1">
        {entries.map(([key, item]) => (
          <div key={key} className="flex gap-2.5">
            <dt className="shrink-0 font-medium text-ink-3">{key}</dt>
            <dd className="min-w-0 flex-1">
              <JsonView value={item} depth={depth + 1} />
            </dd>
          </div>
        ))}
      </dl>
    )
  }
  return <span className="text-ink-4">{String(value)}</span>
}

const LONG_TEXT_THRESHOLD = 280

function LongText({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false)
  if (text.length <= LONG_TEXT_THRESHOLD) {
    return <span className="break-words whitespace-pre-wrap text-ink">{text}</span>
  }
  return (
    <div>
      <span className="break-words whitespace-pre-wrap text-ink">
        {expanded ? text : `${text.slice(0, LONG_TEXT_THRESHOLD)}…`}
      </span>
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="focus-ring ml-2 rounded font-sans text-micro font-medium text-blue hover:underline"
      >
        {expanded ? '收起' : `展开全部 ${text.length} 字`}
      </button>
    </div>
  )
}
