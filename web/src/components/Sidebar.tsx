/**
 * 左侧栏导航。
 *
 * 分两组：**对话**是干活的地方（控制台默认落点），**审计**是这个项目真正的差异所在。
 * 只读模式下对话不可用，那时审计就是全部。
 *
 * 这里刻意**不显示工作区的绝对路径**——一整条 `C:\Users\...\project` 挤在侧栏里
 * 既难看又没信息量。要显示就显示目录名，完整路径留在 API 响应里。约定的落点在
 * `lib/paths.ts`。
 */
import type { ConversationRecord, MetaResponse } from '../lib/types'
import { workspaceName } from '../lib/paths'
import { hrefFor, type Route } from '../lib/router'

export function Sidebar({
  route,
  meta,
  sessionCount,
  compareWith,
  conversation,
}: {
  route: Route
  meta: MetaResponse
  sessionCount: number
  compareWith: string | null
  conversation: ConversationRecord | null
}) {
  const readOnly = meta.server.read_only
  const live = conversation?.status === 'idle' || conversation?.status === 'running'
  const busy = conversation?.busy ?? false

  return (
    <aside className="sidebar flex w-60 shrink-0 flex-col">
      <div className="px-5 pt-6 pb-5">
        <a href={hrefFor({ name: 'chat' })} className="focus-ring block rounded">
          <div className="text-heading font-semibold tracking-tight text-ink">DM-Code-Agent</div>
          <div className="mt-0.5 text-micro text-ink-3">可审计控制台</div>
        </a>
      </div>

      <nav className="flex-1 space-y-6 px-3">
        <Group label="执行">
          <Item
            href={readOnly ? undefined : hrefFor({ name: 'chat' })}
            active={route.name === 'chat'}
            icon={<IconChat />}
            label="对话"
            hint={
              readOnly
                ? '只读模式下不可用'
                : live
                  ? `${conversation?.completed_turns ?? 0}/${conversation?.submitted_turns ?? 0} 轮`
                  : undefined
            }
            muted={readOnly}
            indicator={live ? (busy ? 'busy' : 'live') : undefined}
          />
        </Group>

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
      </nav>

      <div className="divider-soft border-t px-5 py-4">
        <div className="mb-2 truncate text-micro text-ink-3" title="agent 读写文件的目录">
          工作区 · <span className="font-mono text-ink-2">{workspaceName(meta)}</span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span
            className={`chip ${
              readOnly
                ? 'border-blue/25 bg-blue/10 text-blue-ink'
                : 'border-orange/25 bg-orange/10 text-orange-ink'
            }`}
            title={
              readOnly
                ? '只读模式：只提供审计能力，不能发起对话或分叉'
                : '完整模式：agent 会在工作区里真实读写文件'
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
  indicator,
}: {
  href?: string
  active: boolean
  icon: React.ReactNode
  label: string
  badge?: string
  hint?: string
  muted?: boolean
  indicator?: 'live' | 'busy'
}) {
  // 选中态用「左侧一条主色竖线 + 淡底」而不是整块白卡片——在浅色侧栏上更收敛，
  // 也不会因为卡片阴影而把导航项抬得比内容还抢眼。
  const base = 'nav-item relative flex items-center gap-2.5 rounded-control px-2.5 py-2'
  const tone = active
    ? 'nav-item-active text-ink'
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
      {indicator && (
        <span
          className={`size-1.5 shrink-0 rounded-full ${
            indicator === 'busy' ? 'animate-pulse bg-blue' : 'bg-green'
          }`}
          title={indicator === 'busy' ? '正在执行一轮' : '对话开着'}
        />
      )}
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

function IconChat() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M2.5 6.5a3 3 0 0 1 3-3h5a3 3 0 0 1 3 3v2a3 3 0 0 1-3 3H7l-3 2.5V11.4A3 3 0 0 1 2.5 8.7z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  )
}

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
