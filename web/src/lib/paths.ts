/**
 * 路径的展示形态。
 *
 * **界面上不出现绝对路径。** 把 `C:\Users\somebody\Desktop\DM\DM-Code-Agent` 这样
 * 一整条怼在侧栏里，既难看又没信息量——本机单用户场景下用户当然知道自己在哪跑。
 *
 * 所以 `meta.server.workspace`（完整路径）在前端**只允许经过这里**。要显示工作区
 * 就用 `workspaceName()`，它拿的是后端算好的目录名。这个模块存在的意义就是给这条
 * 约定一个可 grep 的落点，免得下次又有人把整条路径贴回界面上。
 */
import type { MetaResponse } from './types'

export function workspaceName(meta: MetaResponse): string {
  return meta.server.workspace_name || meta.server.sessions_dir_name || '工作区'
}

/** 会话名里的目录部分（若有）。用于长文件名的两段式显示。 */
export function sessionBasename(name: string): string {
  const cut = name.lastIndexOf('/')
  return cut >= 0 ? name.slice(cut + 1) : name
}
