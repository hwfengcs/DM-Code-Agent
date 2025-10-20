'use client';

const DEFAULT_API_BASE = 'http://localhost:5000';

const stripTrailingSlash = (value: string) => value.replace(/\/$/, '');
const ensureLeadingSlash = (value: string) => (value.startsWith('/') ? value : `/${value}`);

export const API_BASE_URL = stripTrailingSlash(
  process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_API_BASE,
);

export function buildApiUrl(path: string): string {
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path;
  }
  return `${API_BASE_URL}${ensureLeadingSlash(path)}`;
}

export async function fetchJson<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers as HeadersInit | undefined);
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json');
  }
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(buildApiUrl(path), {
    mode: 'cors',
    ...init,
    headers,
  });

  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    const fallback = (await response.text()).trim();
    const message = fallback || `服务返回非 JSON 响应（状态码 ${response.status}）`;
    throw new Error(message);
  }

  const data = (await response.json()) as T;

  if (!response.ok) {
    const message =
      (data && typeof data === 'object' && 'message' in data
        ? (data as Record<string, unknown>).message
        : null) || `请求失败，状态码 ${response.status}`;
    throw new Error(String(message));
  }

  return data;
}
