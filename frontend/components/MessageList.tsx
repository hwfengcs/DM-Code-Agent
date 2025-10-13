'use client';

import { useState } from 'react';
import type { ReactNode } from 'react';
import { cn, formatTimestamp } from '@/lib/utils';
import type { ChatMessage } from '@/types';
import CodeBlock from './CodeBlock';

interface MessageListProps {
  messages: ChatMessage[];
  loading: boolean;
}

export default function MessageList({ messages, loading }: MessageListProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const toggleExpand = (key: string) => {
    setExpanded((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  if (messages.length === 0 && !loading) {
    return (
      <div className="flex items-center justify-center py-16 text-sm text-slate-400">
        还没有消息，开始向 agent 提问吧。
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {messages.map((message, index) => (
        <article
          key={`${message.timestamp}-${index}`}
          className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
        >
          <header className="mb-2 flex items-baseline justify-between text-xs text-slate-400">
            <span className="font-medium text-slate-600">
              {message.role === 'user' ? '用户' : 'DM Agent'}
            </span>
            <time>{formatTimestamp(message.timestamp)}</time>
          </header>
          <MessageBody
            messageKey={`${message.timestamp}-${index}`}
            content={message.content}
            expanded={!!expanded[`${message.timestamp}-${index}`]}
            onToggle={toggleExpand}
          />

          {message.steps && message.steps.length > 0 && (
            <div className="mt-3 space-y-1 rounded-lg bg-slate-50 p-3 text-xs text-slate-500">
              <div className="font-medium text-slate-600">关键步骤</div>
              {message.steps.slice(-5).map((step) => (
                <div key={`${step.step_num}-${step.action}`}>
                  <span className="text-slate-600">步骤 {step.step_num}:</span>{' '}
                  <span className="text-slate-500">
                    {step.action || '思考'}
                    {step.observation ? ` → ${step.observation}` : ''}
                  </span>
                </div>
              ))}
            </div>
          )}
        </article>
      ))}

      {loading && (
        <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-400">
          Agent 正在处理中...
        </div>
      )}
    </div>
  );
}

interface MessageBodyProps {
  messageKey: string;
  content: string;
  expanded: boolean;
  onToggle: (key: string) => void;
}

function MessageBody({ messageKey, content, expanded, onToggle }: MessageBodyProps) {
  const shouldCollapse = content.length > 600 || content.split('\n').length > 12;

  return (
    <div className="relative">
      <div
        className={cn(
          'whitespace-pre-wrap text-sm leading-relaxed text-slate-700 transition-all',
          shouldCollapse && !expanded && 'max-h-48 overflow-hidden pr-1'
        )}
      >
        {renderContent(content)}
      </div>
      {shouldCollapse && !expanded && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-white to-transparent" />
      )}
      {shouldCollapse && (
        <div className="mt-3 text-right">
          <button
            onClick={() => onToggle(messageKey)}
            className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-500 transition hover:bg-slate-200"
          >
            {expanded ? '收起内容' : '展开全部'}
          </button>
        </div>
      )}
    </div>
  );
}

function renderContent(content: string) {
  const codeBlockRegex = /```(\w+)?\n([\s\S]*?)```/g;
  const parts: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = codeBlockRegex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      parts.push(
        <span key={`text-${lastIndex}`}>
          {content.substring(lastIndex, match.index)}
        </span>
      );
    }

    const language = match[1] || 'text';
    const code = match[2];
    parts.push(
      <CodeBlock key={`code-${match.index}`} language={language} code={code} />
    );

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < content.length) {
    parts.push(
      <span key={`text-${lastIndex}`}>
        {content.substring(lastIndex)}
      </span>
    );
  }

  return parts.length > 0 ? parts : content;
}
