'use client';

import { useState, useEffect } from 'react';
import { Search, Play, Info, Globe } from 'lucide-react';
import { cn } from '@/lib/utils';
import { fetchJson } from '@/lib/api';
import type { Tool } from '@/types';

export default function ToolsTab() {
  const [tools, setTools] = useState<Tool[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadTools();
  }, []);

  const loadTools = async () => {
    try {
      const data = await fetchJson<{ status: string; tools?: Tool[] }>('/api/tools');
      if (data.status === 'success') {
        setTools(data.tools || []);
      }
    } catch (error) {
      console.error('加载工具失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const filteredTools = tools.filter((tool) =>
    tool.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    tool.description.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const mcpTools = filteredTools.filter((t) => t.is_mcp);
  const regularTools = filteredTools.filter((t) => !t.is_mcp);

  return (
    <div className="p-4">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-primary-text mb-2">
          🔧 可用工具 ({tools.length})
        </h3>
        <p className="text-xs text-muted-text">
          查看和使用所有可用的工具
        </p>
      </div>

      {/* 搜索框 */}
      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-text" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="搜索工具..."
          className="w-full pl-10 pr-4 py-2 bg-elevated-bg border border-border-color rounded-lg text-sm text-primary-text placeholder:text-muted-text focus:outline-none focus:border-accent-primary transition-colors"
        />
      </div>

      {loading ? (
        <div className="text-center py-8 text-muted-text">加载中...</div>
      ) : (
        <div className="space-y-4">
          {/* 常规工具 */}
          {regularTools.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-secondary-text mb-2 uppercase">
                内置工具
              </h4>
              <div className="space-y-2">
                {regularTools.map((tool) => (
                  <ToolCard key={tool.name} tool={tool} />
                ))}
              </div>
            </div>
          )}

          {/* MCP 工具 */}
          {mcpTools.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-secondary-text mb-2 uppercase flex items-center gap-1">
                <Globe className="w-3 h-3" />
                MCP 工具
              </h4>
              <div className="space-y-2">
                {mcpTools.map((tool) => (
                  <ToolCard key={tool.name} tool={tool} isMcp />
                ))}
              </div>
            </div>
          )}

          {filteredTools.length === 0 && (
            <div className="text-center py-8 text-muted-text text-sm">
              没有找到匹配的工具
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface ToolCardProps {
  tool: Tool;
  isMcp?: boolean;
}

function ToolCard({ tool, isMcp }: ToolCardProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="p-3 bg-elevated-bg border border-border-color rounded-lg hover:border-accent-primary/50 transition-all card-hover">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h5 className="text-sm font-medium text-primary-text truncate">
              {tool.name}
            </h5>
            {isMcp && (
              <span className="px-1.5 py-0.5 bg-accent-primary/20 text-neon-purple text-xs rounded">
                MCP
              </span>
            )}
          </div>
          <p className={cn(
            'text-xs text-secondary-text',
            !expanded && 'line-clamp-2'
          )}>
            {tool.description}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 mt-2">
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-accent-primary hover:text-accent-secondary transition-colors flex items-center gap-1"
        >
          <Info className="w-3 h-3" />
          {expanded ? '收起' : '详情'}
        </button>
        <button className="text-xs text-success hover:text-green-400 transition-colors flex items-center gap-1">
          <Play className="w-3 h-3" />
          使用
        </button>
      </div>
    </div>
  );
}
