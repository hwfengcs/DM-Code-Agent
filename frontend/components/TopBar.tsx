'use client';

import { useState, useEffect } from 'react';
import { Settings, User, Moon, Sun } from 'lucide-react';
import { cn } from '@/lib/utils';

interface TopBarProps {
  agentStatus?: 'idle' | 'thinking' | 'executing' | 'error';
}

export default function TopBar({ agentStatus = 'idle' }: TopBarProps) {
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');

  const statusConfig = {
    idle: { text: 'Agent 就绪', color: 'bg-success', animation: '' },
    thinking: { text: '思考中...', color: 'bg-accent-primary', animation: 'animate-pulse-dot' },
    executing: { text: '执行工具中...', color: 'bg-info', animation: 'animate-pulse' },
    error: { text: '错误', color: 'bg-error', animation: 'animate-pulse' },
  };

  const currentStatus = statusConfig[agentStatus];

  return (
    <div className="h-[60px] bg-secondary-bg border-b border-border-color flex items-center justify-between px-6">
      {/* 左侧 Logo */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-gradient-primary flex items-center justify-center">
          <span className="text-2xl">🤖</span>
        </div>
        <div>
          <h1 className="text-lg font-bold gradient-text">DM Agent</h1>
          <p className="text-xs text-muted-text">智能代码助手</p>
        </div>
      </div>

      {/* 中间状态指示器 */}
      <div className="flex items-center gap-2">
        <div className={cn(
          'w-3 h-3 rounded-full',
          currentStatus.color,
          currentStatus.animation
        )} />
        <span className="text-sm text-secondary-text">{currentStatus.text}</span>
      </div>

      {/* 右侧操作按钮 */}
      <div className="flex items-center gap-2">
        <button
          className="w-10 h-10 rounded-lg bg-elevated-bg hover:bg-border-color transition-colors flex items-center justify-center"
          title="设置"
        >
          <Settings className="w-5 h-5 text-secondary-text" />
        </button>
        <button
          className="w-10 h-10 rounded-lg bg-elevated-bg hover:bg-border-color transition-colors flex items-center justify-center"
          title="用户"
        >
          <User className="w-5 h-5 text-secondary-text" />
        </button>
        <button
          className="w-10 h-10 rounded-lg bg-elevated-bg hover:bg-border-color transition-colors flex items-center justify-center"
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          title={theme === 'dark' ? '切换到亮色主题' : '切换到暗色主题'}
        >
          {theme === 'dark' ? (
            <Moon className="w-5 h-5 text-secondary-text" />
          ) : (
            <Sun className="w-5 h-5 text-secondary-text" />
          )}
        </button>
      </div>
    </div>
  );
}
