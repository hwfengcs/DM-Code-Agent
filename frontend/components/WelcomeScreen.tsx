'use client';

import { Sparkles, Code, FileSearch, TestTube } from 'lucide-react';
import { generateId } from '@/lib/utils';

interface WelcomeScreenProps {
  onStartChat: (sessionId: string) => void;
}

export default function WelcomeScreen({ onStartChat }: WelcomeScreenProps) {
  const quickTasks = [
    {
      icon: Code,
      title: '创建代码',
      description: '创建一个计算器程序',
      color: 'from-blue-500 to-cyan-500',
    },
    {
      icon: FileSearch,
      title: '分析项目',
      description: '分析 main.py 的代码结构',
      color: 'from-purple-500 to-pink-500',
    },
    {
      icon: TestTube,
      title: '运行测试',
      description: '运行项目的测试用例',
      color: 'from-green-500 to-emerald-500',
    },
  ];

  const handleQuickTask = (description: string) => {
    // 触发新对话
    const newSessionId = generateId();
    onStartChat(newSessionId);
  };

  return (
    <div className="flex-1 flex items-center justify-center bg-primary-bg">
      <div className="max-w-2xl mx-auto text-center px-8">
        {/* Logo 和标题 */}
        <div className="mb-8 animate-breathing">
          <div className="inline-block p-6 rounded-2xl bg-gradient-primary shadow-glow-lg mb-4">
            <Sparkles className="w-16 h-16 text-white" />
          </div>
          <h1 className="text-4xl font-bold gradient-text mb-2">DM Code Agent</h1>
          <p className="text-xl text-secondary-text">你的智能代码助手</p>
        </div>

        {/* 主要 CTA */}
        <button
          onClick={() => onStartChat(generateId())}
          className="w-full max-w-md mx-auto h-14 bg-gradient-primary hover:shadow-glow-md rounded-xl font-medium text-lg text-white transition-all button-hover mb-8"
        >
          开始新对话
        </button>

        {/* 快速任务 */}
        <div className="mb-4">
          <p className="text-sm text-muted-text mb-4">或选择快速任务：</p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {quickTasks.map((task, index) => (
              <button
                key={index}
                onClick={() => handleQuickTask(task.description)}
                className="p-4 rounded-lg bg-elevated-bg border border-border-color hover:border-accent-primary transition-all card-hover text-left"
              >
                <div className={`inline-flex p-2 rounded-lg bg-gradient-to-r ${task.color} mb-2`}>
                  <task.icon className="w-5 h-5 text-white" />
                </div>
                <h3 className="text-sm font-semibold text-primary-text mb-1">{task.title}</h3>
                <p className="text-xs text-secondary-text">{task.description}</p>
              </button>
            ))}
          </div>
        </div>

        {/* 提示信息 */}
        <div className="mt-8 text-xs text-muted-text">
          💡 提示：支持 DeepSeek、OpenAI、Claude、Gemini 等多个 LLM 提供商
        </div>
      </div>
    </div>
  );
}
