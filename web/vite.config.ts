import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// 产物直接落进 Python 包里，这样 `pip install dm-code-agent[web]` 拿到的 wheel
// 自带前端，终端用户不需要 Node。
// base 用相对路径：index.html 对 JS / CSS / 字体的引用不依赖挂载点。
// 这不等于能纯静态托管——数据全部来自同源的 /api（绝对路径，见 src/lib/api.ts），
// 单独把产物放上 GitHub Pages 读不到任何会话。见 docs/web.md「前端构建与托管边界」。
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: './',
  build: {
    outDir: '../dm_agent/server/static',
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5173,
    // 开发时前端在 5173、后端在 8765，代理掉 /api 就不用管 CORS 和 token 传递方式。
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
      },
    },
  },
})
