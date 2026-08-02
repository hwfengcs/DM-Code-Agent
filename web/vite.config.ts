import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// 产物直接落进 Python 包里，这样 `pip install dm-code-agent[web]` 拿到的 wheel
// 自带前端，终端用户不需要 Node。
// base 用相对路径：既能被 uvicorn 挂在 / 下，也能被静态托管在
// GitHub Pages 的子路径（/<repo>/）下，不用为两种部署各出一份构建。
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
