'use client';

import { useState } from 'react';
import ChatArea from '@/components/ChatArea';
import { generateId } from '@/lib/utils';

export default function Home() {
  const [sessionId, setSessionId] = useState<string>(() => generateId());

  const handleNewSession = () => {
    setSessionId(generateId());
  };

  return (
    <main className="relative min-h-screen overflow-hidden bg-gradient-to-br from-[#f5f8ff] via-white to-[#f1f5ff] text-slate-900">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(120,145,255,0.22),transparent_55%)]" />
      <div className="pointer-events-none absolute bottom-[-20%] right-[-10%] h-[320px] w-[320px] rounded-full bg-[radial-gradient(circle,_rgba(255,170,220,0.25),transparent_65%)] blur-3xl" />

      <div className="relative mx-auto flex w-full max-w-[1920px] flex-col gap-10 px-12 py-12 xl:px-20">
        <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="space-y-2">
            <p className="inline-flex items-center gap-2 rounded-full bg-white/70 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.3em] text-slate-400 shadow-sm">
              DM Agent
            </p>
            <h1 className="text-4xl font-semibold tracking-tight text-slate-900">
              智能代码助手面板
            </h1>
            <p className="max-w-xl text-sm text-slate-500">
              在左侧输入你的需求，右侧将实时呈现执行进度、状态与详细日志。保持专注，剩下的交给 Agent。
            </p>
          </div>
          <button
            onClick={handleNewSession}
            className="inline-flex items-center justify-center rounded-full bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 px-6 py-2 text-sm font-medium text-white shadow-lg shadow-indigo-200 transition hover:brightness-105"
          >
            开启新会话
          </button>
        </header>

        <section className="rounded-[32px] border border-white/60 bg-white/80 p-8 shadow-2xl shadow-indigo-100 backdrop-blur-lg">
          <ChatArea key={sessionId} sessionId={sessionId} />
        </section>
      </div>
    </main>
  );
}
