'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { io } from 'socket.io-client';
import { Send } from 'lucide-react';
import { cn } from '@/lib/utils';
import { API_BASE_URL, fetchJson } from '@/lib/api';
import MessageList from './MessageList';
import type { ChatMessage, ExecutionStep } from '@/types';

interface ChatAreaProps {
  sessionId: string;
}

interface StepUpdatePayload {
  session_id: string;
  step: ExecutionStep;
}

const SOCKET_NAMESPACE = '/api/stream';

export default function ChatArea({ sessionId }: ChatAreaProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [liveSteps, setLiveSteps] = useState<ExecutionStep[]>([]);
  const [agentState, setAgentState] = useState<'idle' | 'running'>('idle');

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    setMessages([]);
    setInput('');
    setLiveSteps([]);
    setAgentState('idle');
  }, [sessionId]);

  useEffect(() => {
    const socket = io(`${API_BASE_URL}${SOCKET_NAMESPACE}`, {
      path: '/socket.io',
      transports: ['websocket'],
    });

    const subscribe = () => socket.emit('subscribe', { session_id: sessionId });

    socket.on('connect', subscribe);
    if (socket.connected) {
      subscribe();
    }

    socket.on('step_update', (payload: StepUpdatePayload) => {
      if (!payload || payload.session_id !== sessionId || !payload.step) return;

      setAgentState('running');
      setLiveSteps((prev) => {
        const filtered = prev.filter((item) => item.step_num !== payload.step.step_num);
        const next = [...filtered, payload.step].sort((a, b) => a.step_num - b.step_num);
        return next.slice(-16);
      });
    });

    return () => {
      socket.off('connect', subscribe);
      socket.off('step_update');
      socket.disconnect();
    };
  }, [sessionId]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMessage: ChatMessage = {
      role: 'user',
      content: input,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);
    setAgentState('running');
    setLiveSteps([]);

    try {
      const data = await fetchJson<{
        status: string;
        response: string;
        message?: string;
        steps?: ChatMessage['steps'];
      }>('/api/chat', {
        method: 'POST',
        body: JSON.stringify({
          message: userMessage.content,
          session_id: sessionId,
        }),
      });

      if (data.status !== 'success') {
        throw new Error(data.message || '请求失败');
      }

      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: data.response,
        timestamp: new Date().toISOString(),
        steps: data.steps,
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error('发送消息失败:', error);
      const errorMessage: ChatMessage = {
        role: 'assistant',
        content: `抱歉，发生了错误：${error instanceof Error ? error.message : '未知错误'}`,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
      setAgentState('idle');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const planSteps = useMemo(() => {
    const recentWithSteps = [...messages]
      .reverse()
      .find((msg) => msg.role === 'assistant' && msg.steps && msg.steps.length > 0);
    if (recentWithSteps?.steps?.length) {
      return recentWithSteps.steps;
    }
    return liveSteps;
  }, [messages, liveSteps]);

  const planDisplay = planSteps.slice(0, 8);
  const completedSteps = planDisplay.filter(
    (step) => typeof step.observation === 'string' && step.observation.trim() !== ''
  ).length;

  const statusSteps = liveSteps.length > 0 ? liveSteps.slice(-6) : planDisplay.slice(-6);

  return (
    <div className="grid gap-8 lg:grid-cols-[420px,minmax(0,1fr)]">
      <div className="space-y-6">
        <section className="rounded-[28px] border border-white/70 bg-gradient-to-br from-white via-sky-50 to-white p-6 shadow-lg shadow-sky-100">
          <header className="mb-4 space-y-1">
            <span className="inline-flex items-center gap-2 rounded-full bg-white/80 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.35em] text-slate-400 shadow-sm">
              Prompt
            </span>
            <h2 className="text-lg font-semibold text-slate-700">输入任务</h2>
            <p className="text-xs text-slate-400">描述你希望 agent 完成的事情，Shift+Enter 换行</p>
          </header>
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="例如：实现红黑树，并提供插入、删除、查找的测试用例。"
            className={cn(
              'h-44 w-full resize-none rounded-2xl border border-white/70 bg-white/80 px-4 py-3 text-sm text-slate-800 shadow-inner transition focus:border-indigo-200 focus:outline-none focus:ring-2 focus:ring-indigo-100',
              loading && 'opacity-60'
            )}
            disabled={loading}
          />
          <div className="mt-4 flex items-center justify-between text-xs text-slate-400">
            <span>{input.length > 0 ? `${input.length} 个字符` : '输入后按 Enter 发送请求'}</span>
            <button
              onClick={handleSend}
              disabled={!input.trim() || loading}
              className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 px-5 py-2 text-xs font-semibold text-white shadow-md transition hover:brightness-105 disabled:opacity-40"
            >
              <Send className="h-4 w-4" />
              发送请求
            </button>
          </div>
        </section>

        <section className="rounded-[28px] border border-white/70 bg-white/85 p-6 shadow-lg shadow-indigo-100">
          <header className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-slate-600">📋 执行计划</h2>
              {planDisplay.length > 0 ? (
                <p className="text-xs text-slate-400">
                  计划进度：{completedSteps}/{planDisplay.length} 步骤已完成
                </p>
              ) : (
                <p className="text-xs text-slate-400">发送指令后将自动生成计划</p>
              )}
            </div>
            <span className="rounded-full bg-gradient-to-r from-indigo-100 to-purple-100 px-4 py-1 text-[11px] font-medium text-indigo-500">
              {planDisplay.length > 0 ? '实时同步' : '待生成'}
            </span>
          </header>

          <div className="space-y-3 text-sm text-slate-600 max-h-[45vh] overflow-y-auto pr-1">
            {planDisplay.length > 0 ? (
              planDisplay.map((step) => {
                const isCompleted =
                  typeof step.observation === 'string' && step.observation.trim() !== '';
                const marker = isCompleted ? '✓' : '○';
                const detail = step.thought || step.observation || '';
                return (
                  <div
                    key={`${step.step_num}-${step.action}`}
                    className={cn(
                      'rounded-2xl border px-4 py-3 shadow-sm',
                      isCompleted
                        ? 'border-emerald-100 bg-gradient-to-r from-emerald-50 via-white to-emerald-50/40'
                        : 'border-slate-100 bg-white/80'
                    )}
                  >
                    <p className="text-sm font-medium text-slate-600">
                      {marker} 步骤 {step.step_num}: {step.action || '计划中'}
                      {detail ? ` - ${detail}` : ''}
                    </p>
                  </div>
                );
              })
            ) : (
              <p className="text-sm text-slate-400">暂无计划。</p>
            )}
          </div>
        </section>
      </div>

      <div className="space-y-6">
        <section className="rounded-[28px] border border-white/70 bg-white/85 p-6 shadow-xl shadow-indigo-100">
          <header className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-slate-600">运行状态</h2>
              <p className="text-xs text-slate-400">实时查看当前执行步骤与反馈</p>
            </div>
            <span
              className={cn(
                'inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium shadow-sm',
                agentState === 'running'
                  ? 'bg-gradient-to-r from-emerald-100 to-emerald-50 text-emerald-600 animate-pulse'
                  : 'bg-slate-100 text-slate-500'
              )}
            >
              <span className="h-2 w-2 rounded-full bg-current" />
              {agentState === 'running' ? '执行中' : '空闲'}
            </span>
          </header>

          <div className="mt-4 max-h-[40vh] space-y-3 overflow-y-auto pr-1">
            {statusSteps.length > 0 ? (
              statusSteps.map((step, index) => {
                const isLatest = index === statusSteps.length - 1;
                return (
                  <div
                    key={`${step.step_num}-${step.action}-status-${index}`}
                    className={cn(
                      'rounded-2xl border border-slate-100 p-4 text-sm shadow-sm transition',
                      isLatest
                        ? 'bg-gradient-to-r from-emerald-50 via-emerald-50 to-transparent'
                        : 'bg-white/80'
                    )}
                  >
                    <div className="flex items-center justify-between text-xs text-slate-400">
                      <span className="font-semibold text-slate-500">步骤 {step.step_num}</span>
                      <span>{step.action || '执行中'}</span>
                    </div>
                    {step.observation && (
                      <p className="mt-2 text-sm leading-relaxed text-slate-600">
                        {step.observation}
                      </p>
                    )}
                  </div>
                );
              })
            ) : (
              <p className="text-sm text-slate-400">等待任务开始，执行详情将展示在此处。</p>
            )}
          </div>
        </section>

        <section className="rounded-[28px] border border-white/70 bg-white/85 p-6 shadow-lg shadow-indigo-100">
          <header className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-600">运行日志</h2>
            <span className="text-xs text-slate-400">最新回复在底部</span>
          </header>
          <div className="mt-4 max-h-[45vh] overflow-y-auto pr-1">
            <MessageList messages={messages} loading={loading} />
            <div ref={messagesEndRef} />
          </div>
        </section>
      </div>
    </div>
  );
}
