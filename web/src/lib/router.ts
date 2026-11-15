/**
 * 极简 hash 路由。
 *
 * 用 hash 而不是 history API 是有意的：路由完全在浏览器里解析，服务端只需要交付
 * 一份 index.html，`#/run/foo.jsonl` 这种深链不依赖任何服务端重写规则。
 * 这不等于能纯静态托管——数据仍来自同源的 `/api`，见 docs/web.md「前端构建与托管边界」。
 *
 * 默认路由是**对话**：这是控制台的主界面。只读模式下 `App` 会把它换成会话库——
 * 那时候发起对话本来就不可用，落在一个只会显示 403 的页面上没有意义。
 */
import { useEffect, useState } from 'react'

export type Route =
  | { name: 'chat' }
  | { name: 'list' }
  | { name: 'run'; session: string }
  | { name: 'diff'; a: string; b: string }

export function parseHash(hash: string): Route {
  const raw = hash.replace(/^#/, '')
  const [path, search = ''] = raw.split('?')
  const params = new URLSearchParams(search)
  const segments = (path ?? '').split('/').filter(Boolean)

  if (segments[0] === 'run' && segments[1]) {
    // 会话名可能含子目录，decode 之后按原样交给后端。
    return { name: 'run', session: decodeURIComponent(segments.slice(1).join('/')) }
  }
  if (segments[0] === 'diff') {
    return { name: 'diff', a: params.get('a') ?? '', b: params.get('b') ?? '' }
  }
  if (segments[0] === 'sessions') {
    return { name: 'list' }
  }
  // `#/new` 是上一版「新建运行」的地址，能力已并入对话。老书签不该 404。
  return { name: 'chat' }
}

export function hrefFor(route: Route): string {
  switch (route.name) {
    case 'run':
      return `#/run/${encodeURIComponent(route.session)}`
    case 'diff':
      return `#/diff?a=${encodeURIComponent(route.a)}&b=${encodeURIComponent(route.b)}`
    case 'list':
      return '#/sessions'
    default:
      return '#/'
  }
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash))

  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  return route
}
