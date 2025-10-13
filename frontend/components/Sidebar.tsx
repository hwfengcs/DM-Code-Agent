'use client';

import { useState, useEffect } from 'react';
import { Plus, MessageSquare, FolderOpen, FlaskConical, BarChart, Globe, FileText, Lightbulb } from 'lucide-react';
import { cn, formatTimestamp, truncateText } from '@/lib/utils';
import { fetchJson } from '@/lib/api';
import type { ChatSession } from '@/types';

interface SidebarProps {
  sessionId: string | null;
  onNewChat: () => void;
  onSelectSession: (id: string) => void;
}

export default function Sidebar({ sessionId, onNewChat, onSelectSession }: SidebarProps) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(false);

  // 加载对话历史
  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    try {
      setLoading(true);
      const data = await fetchJson<{ status: string; history?: ChatSession[] }>('/api/history');
      if (data.status === 'success') {
        setSessions(data.history || []);
      }
    } catch (error) {
      console.error('加载历史失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const quickActions = [
    { icon: FolderOpen, label: '文件操作', color: 'text-blue-400' },
    { icon: FlaskConical, label: '运行测试', color: 'text-green-400' },
    { icon: BarChart, label: '代码分析', color: 'text-purple-400' },
    { icon: Globe, label: 'MCP 工具', color: 'text-cyan-400' },
  ];

  return (
    <div className="w-[260px] bg-secondary-bg border-r border-border-color flex flex-col">
      {/* 对话历史区域 */}
      <div className="flex-1 overflow-y-auto p-4">
        <div className="mb-4">
          <h3 className="text-sm font-semibold text-primary-text mb-3">📝 对话历史</h3>
          <div className="space-y-2">
            {loading ? (
              <div className="text-center py-4 text-muted-text">加载中...</div>
            ) : sessions.length === 0 ? (
              <div className="text-center py-4 text-muted-text text-sm">暂无历史记录</div>
            ) : (
              sessions.map((session) => (
                <button
                  key={session.id}
                  onClick={() => onSelectSession(session.id)}
                  className={cn(
                    'w-full p-3 rounded-lg bg-elevated-bg border border-border-color text-left transition-all card-hover',
                    sessionId === session.id && 'border-l-4 border-l-accent-primary'
                  )}
                >
                  <div className="flex items-start gap-2">
                    <MessageSquare className="w-4 h-4 text-accent-primary mt-0.5 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-primary-text truncate">{truncateText(session.title, 25)}</p>
                      <p className="text-xs text-muted-text mt-1">{formatTimestamp(session.time)}</p>
                    </div>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        {/* 新建对话按钮 */}
        <button
          onClick={onNewChat}
          className="w-full h-[42px] bg-gradient-primary hover:shadow-glow-md rounded-lg font-medium text-white transition-all button-hover flex items-center justify-center gap-2"
        >
          <Plus className="w-5 h-5" />
          新建对话
        </button>

        {/* 分割线 */}
        <div className="my-4 h-px bg-border-color" />

        {/* 快捷操作 */}
        <div>
          <h3 className="text-sm font-semibold text-primary-text mb-3">🔧 快捷操作</h3>
          <div className="space-y-1">
            {quickActions.map((action, index) => (
              <button
                key={index}
                className="w-full p-2 rounded-lg hover:bg-elevated-bg transition-colors flex items-center gap-3 text-sm text-secondary-text hover:text-primary-text"
              >
                <action.icon className={cn('w-4 h-4', action.color)} />
                {action.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 底部链接 */}
      <div className="p-4 border-t border-border-color">
        <div className="flex items-center justify-center gap-4 text-xs text-muted-text">
          <button className="hover:text-primary-text transition-colors flex items-center gap-1">
            <FileText className="w-3 h-3" />
            文档
          </button>
          <span>·</span>
          <button className="hover:text-primary-text transition-colors flex items-center gap-1">
            <Lightbulb className="w-3 h-3" />
            示例
          </button>
        </div>
      </div>
    </div>
  );
}

