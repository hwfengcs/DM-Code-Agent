// API 相关类型
export interface ApiResponse<T = any> {
  status: 'success' | 'error';
  message?: string;
  data?: T;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  steps?: ExecutionStep[];
}

export interface ExecutionStep {
  step_num: number;
  thought: string;
  action: string;
  action_input: any;
  observation: string;
}

export interface ChatSession {
  id: string;
  title: string;
  time: string;
  message_count: number;
}

export interface Tool {
  name: string;
  description: string;
  is_mcp: boolean;
}

export interface Config {
  provider: 'deepseek' | 'openai' | 'claude' | 'gemini';
  model: string;
  base_url?: string;
  max_steps: number;
  temperature: number;
}

export interface TaskPlan {
  steps: PlanStep[];
  current_step: number;
  total_steps: number;
  progress: number;
}

export interface PlanStep {
  step_num: number;
  tool_name: string;
  description: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
}

export interface AgentStatus {
  state: 'idle' | 'thinking' | 'executing' | 'error';
  current_task?: string;
  current_step?: string;
  progress?: number;
  token_usage?: number;
  execution_time?: number;
}
