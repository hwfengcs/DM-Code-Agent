import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'DM Code Agent - 智能代码助手',
  description: '基于 ReAct 架构的多模型 AI Code Agent，支持 DeepSeek、OpenAI、Claude、Gemini 等多个 LLM 提供商',
  icons: {
    icon: '/favicon.ico',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" className={inter.variable}>
      <body className="bg-primary-bg text-primary-text antialiased">
        {children}
      </body>
    </html>
  );
}
