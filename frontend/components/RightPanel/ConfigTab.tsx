'use client';

import { useState, useEffect } from 'react';
import { Save, RotateCcw } from 'lucide-react';
import { cn } from '@/lib/utils';
import { fetchJson } from '@/lib/api';
import type { Config } from '@/types';

export default function ConfigTab() {
  const [config, setConfig] = useState<Config>({
    provider: 'deepseek',
    model: 'deepseek-chat',
    base_url: 'https://api.deepseek.com',
    max_steps: 100,
    temperature: 0.7,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      const data = await fetchJson<{ status: string; config?: Config }>('/api/config');
      if (data.status === 'success' && data.config) {
        setConfig(data.config);
      }
    } catch (error) {
      console.error('加载配置失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      const data = await fetchJson<{ status: string; message?: string }>('/api/config', {
        method: 'POST',
        body: JSON.stringify(config),
      });
      alert(data.message || '✓ 配置已保存');
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      alert(`✗ 保存失败: ${message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setConfig({
      provider: 'deepseek',
      model: 'deepseek-chat',
      base_url: 'https://api.deepseek.com',
      max_steps: 100,
      temperature: 0.7,
    });
  };

  if (loading) {
    return <div className="p-4 text-center text-muted-text">加载中...</div>;
  }

  return (
    <div className="p-4">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-primary-text mb-2">⚙️ 配置设置</h3>
        <p className="text-xs text-muted-text">调整 Agent 运行参数</p>
      </div>

      <div className="space-y-4">
        {/* LLM 提供商 */}
        <div>
          <label className="block text-xs font-medium text-secondary-text mb-2">
            LLM 提供商
          </label>
          <select
            value={config.provider}
            onChange={(e) => setConfig({ ...config, provider: e.target.value as any })}
            className="w-full px-3 py-2 bg-elevated-bg border border-border-color rounded-lg text-sm text-primary-text focus:outline-none focus:border-accent-primary transition-colors"
          >
            <option value="deepseek">DeepSeek</option>
            <option value="openai">OpenAI</option>
            <option value="claude">Claude</option>
            <option value="gemini">Gemini</option>
          </select>
        </div>

        {/* 模型名称 */}
        <div>
          <label className="block text-xs font-medium text-secondary-text mb-2">
            模型
          </label>
          <input
            type="text"
            value={config.model}
            onChange={(e) => setConfig({ ...config, model: e.target.value })}
            className="w-full px-3 py-2 bg-elevated-bg border border-border-color rounded-lg text-sm text-primary-text focus:outline-none focus:border-accent-primary transition-colors"
          />
        </div>

        {/* Base URL */}
        {config.provider !== 'gemini' && (
          <div>
            <label className="block text-xs font-medium text-secondary-text mb-2">
              Base URL
            </label>
            <input
              type="text"
              value={config.base_url || ''}
              onChange={(e) => setConfig({ ...config, base_url: e.target.value })}
              placeholder="https://api.example.com"
              className="w-full px-3 py-2 bg-elevated-bg border border-border-color rounded-lg text-sm text-primary-text placeholder:text-muted-text focus:outline-none focus:border-accent-primary transition-colors"
            />
          </div>
        )}

        {/* Temperature 滑块 */}
        <div>
          <label className="block text-xs font-medium text-secondary-text mb-2">
            Temperature <span className="text-muted-text">({config.temperature.toFixed(1)})</span>
          </label>
          <input
            type="range"
            min="0"
            max="2"
            step="0.1"
            value={config.temperature}
            onChange={(e) => setConfig({ ...config, temperature: parseFloat(e.target.value) })}
            className="w-full h-2 bg-border-color rounded-lg appearance-none cursor-pointer accent-accent-primary"
          />
          <div className="flex justify-between text-xs text-muted-text mt-1">
            <span>精确 (0.0)</span>
            <span>创造 (2.0)</span>
          </div>
        </div>

        {/* 最大步骤数 */}
        <div>
          <label className="block text-xs font-medium text-secondary-text mb-2">
            最大步骤数
          </label>
          <input
            type="number"
            min="1"
            max="200"
            value={config.max_steps}
            onChange={(e) => setConfig({ ...config, max_steps: parseInt(e.target.value) })}
            className="w-full px-3 py-2 bg-elevated-bg border border-border-color rounded-lg text-sm text-primary-text focus:outline-none focus:border-accent-primary transition-colors"
          />
        </div>

        {/* 操作按钮 */}
        <div className="flex gap-2 pt-2">
          <button
            onClick={handleSave}
            disabled={saving}
            className={cn(
              'flex-1 h-10 bg-gradient-primary hover:shadow-glow-md rounded-lg font-medium text-sm text-white transition-all button-hover flex items-center justify-center gap-2',
              saving && 'opacity-50 cursor-not-allowed'
            )}
          >
            <Save className="w-4 h-4" />
            {saving ? '保存中...' : '保存配置'}
          </button>
          <button
            onClick={handleReset}
            className="px-4 h-10 bg-elevated-bg hover:bg-border-color rounded-lg font-medium text-sm text-secondary-text hover:text-primary-text transition-all flex items-center gap-2"
          >
            <RotateCcw className="w-4 h-4" />
            重置
          </button>
        </div>
      </div>

      <div className="mt-6 p-3 bg-elevated-bg rounded-lg border border-border-color">
        <p className="text-xs text-muted-text leading-relaxed">
          <strong className="text-secondary-text">提示：</strong>
          修改配置后需要保存才会生效。Gemini 使用官方 SDK，不需要配置 Base URL。
        </p>
      </div>
    </div>
  );
}
