/**
 * 左侧栏导航。
 *
 * 上一版把标题、模式、diff 基准、workspace、新建、刷新六样东西挤在一条顶栏里。
 * 这里按**审计 / 执行**两组拆开——这是本项目最核心的分区：绝大多数使用场景是
 * 事后审计（只读也能用），发起运行反而是次要的、且在只读模式下根本不可用。
 */
import type { MetaResponse } from '../lib/types'
import { hrefFor, type Route } from '../lib/router'

export function Sidebar({
  route,
  meta,
  sessionCount,
  compareWith,
}: {
  route: Route
  meta: MetaResponse
  sessionCount: number
  compareWith: string | null
}) {
  const readOnly = meta.server.read_only

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-line bg-subtle">
      <div className="px-5 pt-6 pb-5">
        <a href={hrefFor({ name: 'list' })} className="block">
          <div className="text-heading font-semibold tracking-tight text-ink">DM-Code-Agent</div>
          <div className="mt-0.5 text-micro text-ink-3">可审计控制台</div>
        </a>
        <div
          className="mt-3 truncate font-mono text-micro text-ink-3"
          title={meta.server.workspace}
          dir="rtl"
        >
          {meta.server.workspace}
        </div>
      </div>

      <nav className="flex-1 space-y-6 px-3">
        <Group label="审计">
          <Item
            href={hrefFor({ name: 'list' })}
            active={route.name === 'list' || route.name === 'run'}
            icon={<IconSessions />}
            label="会话库"
            badge={String(sessionCount)}
          />
          {/* diff 需要两个会话。侧栏只反映基准状态并把人送回会话库挑第二个，
              绝不生成 a===b 的自比较链接。 */}
          <Item
            href={route.name === 'diff' ? undefined : hrefFor({ name: 'list' })}
            active={route.name === 'diff'}
            icon={<IconDiff />}
            label="行为对比"
            hint={compareWith ? `基准 ${compareWith}` : '先在会话库设一个基准'}
            muted={!compareWith && route.name !== 'diff'}
          />
        </Group>

        <Group label="执行">
          <Item
            href={readOnly ? undefined : hrefFor({ name: 'new' })}
            active={route.name === 'new'}
            icon={<IconRun />}
            label="新建运行"
            hint={readOnly ? '只读模式下不可用' : undefined}
            muted={readOnly}
          />
        </Group>
      </nav>

      <div className="border-t border-line px-5 py-4">
        <div className="flex items-center justify-between gap-2">
          <span
            className={`chip ${
              readOnly
                ? 'border-blue/25 bg-blue/10 text-blue-ink'
                : 'border-orange/25 bg-orange/10 text-orange-ink'
            }`}
            title={
              readOnly
                ? '只读模式：只提供审计能力，不能发起运行或分叉'
                : `完整模式：agent 会在 ${meta.server.workspace} 里真实读写文件`
            }
          >
            {readOnly ? '只读' : '可写'}
          </span>
          <span className="font-mono text-micro text-ink-3">v{meta.version}</span>
        </div>
      </div>
    </aside>
  )
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="px-2 pb-1.5 text-micro font-semibold tracking-wide text-ink-4">{label}</div>
      <div className="space-y-0.5">{children}</div>
    </div>
  )
}

function Item({
  href,
  active,
  icon,
  label,
  badge,
  hint,
  muted = false,
}: {
  href?: string
  active: boolean
  icon: React.ReactNode
  label: string
  badge?: string
  hint?: string
  muted?: boolean
}) {
  const base = 'flex items-center gap-2.5 rounded-control px-2.5 py-2 transition-colors'
  const tone = active
    ? 'bg-surface text-ink shadow-card'
    : muted
      ? 'text-ink-4'
      : 'text-ink-2 hover:bg-muted hover:text-ink'

  const content = (
    <>
      <span className={active ? 'text-blue' : 'text-ink-4'}>{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-caption font-medium">{label}</span>
        {hint && <span className="block truncate text-micro text-ink-4">{hint}</span>}
      </span>
      {badge && <span className="shrink-0 tabular-nums text-micro text-ink-3">{badge}</span>}
    </>
  )

  if (!href) {
    return <div className={`${base} ${tone} cursor-not-allowed`}>{content}</div>
  }
  return (
    <a href={href} className={`focus-ring ${base} ${tone}`}>
      {content}
    </a>
  )
}

/* 极简线性图标。16px，1.5 描边，跟随文字颜色。 */

function IconSessions() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M2.5 4.5h11M2.5 8h11M2.5 11.5h7"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  )
}

function IconDiff() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M4.5 13V6.5a2 2 0 0 1 2-2h5M11.5 3 13 4.5 11.5 6M11.5 13V9.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="4.5" cy="13" r="1.25" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  )
}

function IconRun() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M5.5 3.8v8.4a.6.6 0 0 0 .93.5l6.2-4.2a.6.6 0 0 0 0-1l-6.2-4.2a.6.6 0 0 0-.93.5Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  )
}
