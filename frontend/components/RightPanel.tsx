'use client';

import { useState, useEffect } from 'react';
import { X, Wrench, Settings, Activity } from 'lucide-react';
import { cn } from '@/lib/utils';
import ToolsTab from './RightPanel/ToolsTab';
import ConfigTab from './RightPanel/ConfigTab';
import StatusTab from './RightPanel/StatusTab';

interface RightPanelProps {
  activeTab: 'tools' | 'config' | 'status';
  onTabChange: (tab: 'tools' | 'config' | 'status') => void;
  onClose: () => void;
}

export default function RightPanel({ activeTab, onTabChange, onClose }: RightPanelProps) {
  const tabs = [
    { key: 'tools' as const, label: '工具', icon: Wrench },
    { key: 'config' as const, label: '配置', icon: Settings },
    { key: 'status' as const, label: '状态', icon: Activity },
  ];

  return (
    <div className="w-[320px] bg-secondary-bg border-l border-border-color flex flex-col">
      {/* Tab 切换栏 */}
      <div className="h-12 border-b border-border-color flex items-center justify-between px-2">
        <div className="flex items-center gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => onTabChange(tab.key)}
              className={cn(
                'flex items-center gap-2 px-3 py-2 rounded-lg transition-all text-sm font-medium',
                activeTab === tab.key
                  ? 'bg-elevated-bg text-primary-text border-b-2 border-accent-primary'
                  : 'text-secondary-text hover:text-primary-text hover:bg-elevated-bg/50'
              )}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>

        <button
          onClick={onClose}
          className="p-1.5 rounded-lg hover:bg-elevated-bg transition-colors text-muted-text hover:text-primary-text"
          title="关闭面板"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Tab 内容区域 */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === 'tools' && <ToolsTab />}
        {activeTab === 'config' && <ConfigTab />}
        {activeTab === 'status' && <StatusTab />}
      </div>
    </div>
  );
}
