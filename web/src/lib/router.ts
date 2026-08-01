/**
 * 极简 hash 路由。
 *
 * 用 hash 而不是 history API 是有意的：静态托管（GitHub Pages）下没有服务端重写，
 * `#/run/foo.jsonl` 这种深链才能直接分享出去而不 404。同一份构建既能给 uvicorn 用，
 * 也能直接扔上 Pages。
 *
 * 默认路由是**对话**：这是控制台的主界面。只读模式下 `App` 会把它换成会话库——
 * 那时候发起对话本来就不可用，落在一个只会显示 403 的页面上没有意义。
 */
import { useCallback, useEffect, useState } from 'react'

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

export function useRoute(): [Route, (route: Route) => void] {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash))

  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  const navigate = useCallback((next: Route) => {
    window.location.hash = hrefFor(next)
  }, [])

  return [route, navigate]
}
