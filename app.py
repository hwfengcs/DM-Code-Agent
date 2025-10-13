"""Flask Web 应用入口 - 提供前端界面的后端 API"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv

from dm_agent import (
    LLMError,
    ReactAgent,
    Tool,
    create_llm_client,
    default_tools,
    PROVIDER_DEFAULTS,
)
from dm_agent.mcp import MCPManager, load_mcp_config

# 加载环境变量
load_dotenv()

# 创建 Flask 应用
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dm-agent-secret-key')

# 启用 CORS (允许前端跨域访问)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# 创建 SocketIO 实例 (用于 WebSocket 实时通信)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 全局变量
mcp_manager: MCPManager | None = None
tools_cache: List[Tool] = []
sessions: Dict[str, Dict[str, Any]] = {}  # 存储会话信息
conversation_history: Dict[str, List[Dict[str, Any]]] = {}  # 存储对话历史


def get_api_key_for_provider(provider: str) -> str | None:
    """根据提供商获取对应的 API 密钥"""
    provider_env_map = {
        "deepseek": "DEEPSEEK_API_KEY",
        "openai": "OPENAI_API_KEY",
        "claude": "CLAUDE_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }
    env_var = provider_env_map.get(provider.lower())
    return os.getenv(env_var) if env_var else None


def load_config_from_file() -> Dict[str, Any]:
    """从配置文件加载设置"""
    config_file = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
        "max_steps": 100,
        "temperature": 0.7,
    }


def save_config_to_file(config: Dict[str, Any]) -> bool:
    """保存配置到文件"""
    config_file = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def create_step_callback(session_id: str):
    """创建步骤回调函数，用于实时推送执行状态"""
    def callback(step_num: int, step: Any) -> None:
        # 通过 WebSocket 推送步骤更新
        step_data = {
            "step_num": step_num,
            "thought": step.thought,
            "action": step.action,
            "action_input": step.action_input,
            "observation": step.observation,
        }
        socketio.emit('step_update', {
            'session_id': session_id,
            'step': step_data
        }, namespace='/api/stream')
    return callback


# ==================== API 路由 ====================

@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查端点"""
    return jsonify({
        'status': 'ok',
        'message': 'DM Agent API is running'
    })


@app.route('/api/config', methods=['GET'])
def get_config():
    """获取当前配置"""
    config = load_config_from_file()
    return jsonify({
        'status': 'success',
        'config': config
    })


@app.route('/api/config', methods=['POST'])
def update_config():
    """更新配置"""
    try:
        data = request.get_json()

        # 验证必需字段
        required_fields = ['provider', 'model', 'max_steps', 'temperature']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'status': 'error',
                    'message': f'缺少必需字段: {field}'
                }), 400

        # 验证提供商
        if data['provider'] not in ['deepseek', 'openai', 'claude', 'gemini']:
            return jsonify({
                'status': 'error',
                'message': '无效的提供商'
            }), 400

        # 保存配置
        if save_config_to_file(data):
            return jsonify({
                'status': 'success',
                'message': '配置已更新'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': '配置保存失败'
            }), 500

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/tools', methods=['GET'])
def get_tools():
    """获取可用工具列表"""
    tools_info = []
    for tool in tools_cache:
        tools_info.append({
            'name': tool.name,
            'description': tool.description,
            'is_mcp': tool.name.startswith('mcp_')
        })

    return jsonify({
        'status': 'success',
        'tools': tools_info,
        'count': len(tools_info)
    })


@app.route('/api/chat', methods=['POST'])
def chat():
    """处理聊天请求"""
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        session_id = data.get('session_id', str(uuid.uuid4()))

        if not message:
            return jsonify({
                'status': 'error',
                'message': '消息不能为空'
            }), 400

        # 加载配置
        config = load_config_from_file()
        provider = config.get('provider', 'deepseek')
        model = config.get('model', 'deepseek-chat')
        base_url = config.get('base_url', 'https://api.deepseek.com')
        max_steps = config.get('max_steps', 100)
        temperature = config.get('temperature', 0.7)

        # 获取 API 密钥
        api_key = get_api_key_for_provider(provider)
        if not api_key:
            return jsonify({
                'status': 'error',
                'message': f'未找到 {provider.upper()}_API_KEY 环境变量'
            }), 500

        # 创建或获取会话的 Agent
        if session_id not in sessions:
            # 创建新的 Agent
            client = create_llm_client(
                provider=provider,
                api_key=api_key,
                model=model,
                base_url=base_url,
            )

            step_callback = create_step_callback(session_id)

            agent = ReactAgent(
                client,
                tools_cache,
                max_steps=max_steps,
                temperature=temperature,
                step_callback=step_callback,
            )

            sessions[session_id] = {
                'agent': agent,
                'created_at': datetime.now().isoformat(),
            }
            conversation_history[session_id] = []

        agent = sessions[session_id]['agent']

        # 记录用户消息
        conversation_history[session_id].append({
            'role': 'user',
            'content': message,
            'timestamp': datetime.now().isoformat()
        })

        # 执行任务
        try:
            result = agent.run(message)
            final_answer = result.get('final_answer', '')
            steps = result.get('steps', [])

            # 记录 Agent 响应
            conversation_history[session_id].append({
                'role': 'assistant',
                'content': final_answer,
                'timestamp': datetime.now().isoformat(),
                'steps': steps
            })

            return jsonify({
                'status': 'success',
                'session_id': session_id,
                'response': final_answer,
                'steps': steps,
                'step_count': len(steps)
            })

        except LLMError as e:
            return jsonify({
                'status': 'error',
                'message': f'LLM 错误: {str(e)}'
            }), 500

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/history', methods=['GET'])
def get_history():
    """获取对话历史列表"""
    history_list = []

    for session_id, messages in conversation_history.items():
        if messages:
            # 获取第一条用户消息作为标题
            first_message = next((msg for msg in messages if msg['role'] == 'user'), None)
            if first_message:
                title = first_message['content'][:50]  # 截取前50个字符
                history_list.append({
                    'id': session_id,
                    'title': title,
                    'time': first_message['timestamp'],
                    'message_count': len(messages)
                })

    # 按时间倒序排序
    history_list.sort(key=lambda x: x['time'], reverse=True)

    return jsonify({
        'status': 'success',
        'history': history_list
    })


@app.route('/api/history/<session_id>', methods=['GET'])
def get_session_history(session_id: str):
    """获取特定会话的完整历史"""
    if session_id not in conversation_history:
        return jsonify({
            'status': 'error',
            'message': '会话不存在'
        }), 404

    return jsonify({
        'status': 'success',
        'session_id': session_id,
        'messages': conversation_history[session_id]
    })


@app.route('/api/session/<session_id>', methods=['DELETE'])
def delete_session(session_id: str):
    """删除会话"""
    if session_id in sessions:
        # 重置 Agent 对话历史
        sessions[session_id]['agent'].reset_conversation()
        del sessions[session_id]

    if session_id in conversation_history:
        del conversation_history[session_id]

    return jsonify({
        'status': 'success',
        'message': '会话已删除'
    })


@app.route('/api/session/<session_id>/reset', methods=['POST'])
def reset_session(session_id: str):
    """重置会话历史"""
    if session_id in sessions:
        sessions[session_id]['agent'].reset_conversation()

    if session_id in conversation_history:
        conversation_history[session_id] = []

    return jsonify({
        'status': 'success',
        'message': '会话已重置'
    })


# ==================== WebSocket 事件 ====================

@socketio.on('connect', namespace='/api/stream')
def handle_connect():
    """客户端连接"""
    print(f'客户端已连接: {request.sid}')
    emit('connected', {'message': 'WebSocket 连接成功'})


@socketio.on('disconnect', namespace='/api/stream')
def handle_disconnect():
    """客户端断开连接"""
    print(f'客户端已断开: {request.sid}')


@socketio.on('subscribe', namespace='/api/stream')
def handle_subscribe(data):
    """订阅会话更新"""
    session_id = data.get('session_id')
    print(f'客户端订阅会话: {session_id}')
    emit('subscribed', {'session_id': session_id})


# ==================== 应用初始化 ====================

def initialize_app():
    """初始化应用"""
    global mcp_manager, tools_cache

    print("正在初始化 DM Agent Web 应用...")

    # 初始化 MCP 管理器
    try:
        mcp_config = load_mcp_config()
        mcp_manager = MCPManager(mcp_config)

        # 启动所有启用的 MCP 服务器
        print("正在加载 MCP 服务器...")
        started_count = mcp_manager.start_all()
        if started_count > 0:
            print(f"✓ 成功启动 {started_count} 个 MCP 服务器")
        else:
            print("ℹ 未启用 MCP 服务器")

        # 获取包含 MCP 工具的工具列表
        mcp_tools = mcp_manager.get_tools()
        tools_cache = default_tools(include_mcp=True, mcp_tools=mcp_tools)

        if mcp_tools:
            print(f"✓ 加载了 {len(mcp_tools)} 个 MCP 工具")

        print(f"✓ 总共加载了 {len(tools_cache)} 个工具")

    except Exception as e:
        print(f"⚠ MCP 初始化警告: {e}")
        # 即使 MCP 初始化失败，也继续使用默认工具
        tools_cache = default_tools(include_mcp=False)
        print(f"✓ 使用默认工具集 ({len(tools_cache)} 个)")

    print("✓ DM Agent Web 应用初始化完成")


# ==================== 主入口 ====================

if __name__ == '__main__':
    # 初始化应用
    initialize_app()

    # 启动 Flask 应用
    print("\n" + "=" * 70)
    print("DM Agent Web 服务器启动中...".center(70))
    print("=" * 70)
    print("\n访问地址: http://localhost:5000")
    print("API 文档: http://localhost:5000/api/health")
    print("\n按 Ctrl+C 停止服务器\n")

    try:
        # 使用 SocketIO 运行应用 (支持 WebSocket)
        socketio.run(
        socketio.run(
            app,
            host='0.0.0.0',
            port=5000,
            debug=True,
            use_reloader=False,  # 避免 MCP 服务器重复启动
            allow_unsafe_werkzeug=True  # 允许在开发环境中使用 Werkzeug
        )
        )
    finally:
        # 清理 MCP 资源
        if mcp_manager:
            print("\n正在关闭 MCP 服务器...")
            mcp_manager.stop_all()
            print("✓ MCP 服务器已关闭")
