'use client';

import { useState } from 'react';
import { Clock, Cpu, Zap, StopCircle, FileText } from 'lucide-react';
import { cn } from '@/lib/utils';

export default function StatusTab() {
  const [currentTask, setCurrentTask] = useState('分析代码结构');
  const [progress, setProgress] = useState(60);
  const [tokenUsage, setTokenUsage] = useState(1234);
  const [executionTime, setExecutionTime] = useState('00:15');
  const [currentStep, setCurrentStep] = useState(8);
  const [totalSteps, setTotalSteps] = useState(100);

  const steps = [
    { name: '读取文件', status: 'completed' as const, icon: '✓' },
    { name: '解析 AST', status: 'completed' as const, icon: '✓' },
    { name: '提取函数签名', status: 'in_progress' as const, icon: '⏳' },
    { name: '生成报告', status: 'pending' as const, icon: '○' },
  ];

  return (
    <div className="p-4">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-primary-text mb-2">📊 执行状态</h3>
        <p className="text-xs text-muted-text">实时监控 Agent 执行情况</p>
      </div>

      {/* 当前任务 */}
      <div className="mb-4">
        <h4 className="text-xs font-medium text-secondary-text mb-2">当前任务</h4>
        <div className="p-3 bg-elevated-bg border border-border-color rounded-lg">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-2 h-2 bg-info rounded-full animate-pulse" />
            <p className="text-sm text-primary-text">{currentTask}</p>
          </div>

          {/* 进度条 */}
          <div className="space-y-2">
            <div className="flex justify-between text-xs text-muted-text">
              <span>进度</span>
              <span>{progress}%</span>
            </div>
            <div className="h-2 bg-border-color rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-primary progress-bar transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* 步骤详情 */}
      <div className="mb-4">
        <h4 className="text-xs font-medium text-secondary-text mb-2">步骤详情</h4>
        <div className="p-3 bg-elevated-bg border border-border-color rounded-lg space-y-2">
          {steps.map((step, index) => (
            <div key={index} className="flex items-center gap-3">
              <div className={cn(
                'w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium',
                step.status === 'completed' && 'bg-success/20 text-success',
                step.status === 'in_progress' && 'bg-info/20 text-info animate-pulse',
                step.status === 'pending' && 'bg-border-color text-muted-text'
              )}>
                {step.icon}
              </div>
              <span className={cn(
                'text-sm flex-1',
                step.status === 'completed' && 'text-secondary-text line-through',
                step.status === 'in_progress' && 'text-primary-text font-medium',
                step.status === 'pending' && 'text-muted-text'
              )}>
                {step.name}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* 统计信息 */}
      <div className="mb-4">
        <h4 className="text-xs font-medium text-secondary-text mb-2">统计信息</h4>
        <div className="grid grid-cols-2 gap-2">
          <div className="p-3 bg-elevated-bg border border-border-color rounded-lg">
            <div className="flex items-center gap-2 mb-1">
              <Cpu className="w-4 h-4 text-accent-primary" />
              <span className="text-xs text-secondary-text">已用 Token</span>
            </div>
            <p className="text-lg font-semibold text-primary-text">{tokenUsage.toLocaleString()}</p>
          </div>

          <div className="p-3 bg-elevated-bg border border-border-color rounded-lg">
            <div className="flex items-center gap-2 mb-1">
              <Zap className="w-4 h-4 text-warning" />
              <span className="text-xs text-secondary-text">执行步骤</span>
            </div>
            <p className="text-lg font-semibold text-primary-text">{currentStep}/{totalSteps}</p>
          </div>

          <div className="p-3 bg-elevated-bg border border-border-color rounded-lg col-span-2">
            <div className="flex items-center gap-2 mb-1">
              <Clock className="w-4 h-4 text-info" />
              <span className="text-xs text-secondary-text">执行时间</span>
            </div>
            <p className="text-lg font-semibold text-primary-text">{executionTime}</p>
          </div>
        </div>
      </div>

      {/* 操作按钮 */}
      <div className="flex gap-2">
        <button className="flex-1 h-9 bg-error/10 hover:bg-error/20 border border-error rounded-lg font-medium text-sm text-error transition-all flex items-center justify-center gap-2">
          <StopCircle className="w-4 h-4" />
          停止任务
        </button>
        <button className="flex-1 h-9 bg-elevated-bg hover:bg-border-color rounded-lg font-medium text-sm text-secondary-text hover:text-primary-text transition-all flex items-center justify-center gap-2">
          <FileText className="w-4 h-4" />
          查看日志
        </button>
      </div>
    </div>
  );
}
