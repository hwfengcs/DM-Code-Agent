"""MCP 环境诊断工具"""

import subprocess
import sys
import os
import json


def check_command(command: str, args: list = None) -> tuple[bool, str]:
    """检查命令是否可用

    Returns:
        (是否可用, 版本信息或错误信息)
    """
    try:
        cmd = [command] + (args or ['--version'])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            shell=True if sys.platform == 'win32' else False,
            timeout=5
        )
        if result.returncode == 0:
            version = result.stdout.strip().split('\n')[0]
            return True, version
        else:
            return False, result.stderr.strip()
    except FileNotFoundError:
        return False, f"命令 '{command}' 未找到"
    except subprocess.TimeoutExpired:
        return False, "命令执行超时"
    except Exception as e:
        return False, str(e)


def check_mcp_config():
    """检查 MCP 配置文件"""
    config_file = "mcp_config.json"

    if not os.path.exists(config_file):
        return False, "配置文件不存在"

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        servers = config.get('mcpServers', {})
        enabled_count = sum(1 for s in servers.values() if s.get('enabled', True))

        return True, f"配置有效，共 {len(servers)} 个服务器，{enabled_count} 个已启用"
    except json.JSONDecodeError as e:
        return False, f"JSON 格式错误: {e}"
    except Exception as e:
        return False, str(e)


def print_status(name: str, success: bool, message: str):
    """打印状态"""
    status = "✅" if success else "❌"
    print(f"{status} {name}: {message}")


def main():
    """主函数"""
    print("=" * 70)
    print("MCP 环境诊断工具".center(70))
    print("=" * 70)
    print()

    # 检查 Python
    print("📋 检查 Python 环境")
    print_status("Python", True, f"{sys.version.split()[0]}")
    print()

    # 检查 Node.js
    print("📋 检查 Node.js 环境")
    node_ok, node_msg = check_command('node')
    print_status("Node.js", node_ok, node_msg)

    npm_ok, npm_msg = check_command('npm')
    print_status("npm", npm_ok, npm_msg)

    npx_ok, npx_msg = check_command('npx')
    print_status("npx", npx_ok, npx_msg)
    print()

    # 检查 MCP 配置
    print("📋 检查 MCP 配置")
    config_ok, config_msg = check_mcp_config()
    print_status("mcp_config.json", config_ok, config_msg)
    print()

    # 总结
    print("=" * 70)
    all_ok = node_ok and npm_ok and npx_ok and config_ok

    if all_ok:
        print("✅ 所有检查通过！MCP 环境配置正确。")
        print()
        print("你可以运行以下命令启动系统：")
        print("  python main.py")
    else:
        print("❌ 发现问题，请按以下步骤修复：")
        print()

        if not (node_ok and npm_ok and npx_ok):
            print("1. 安装 Node.js:")
            print("   访问 https://nodejs.org/ 下载并安装")
            if sys.platform == 'win32':
                print("   Windows 用户请确保勾选 'Add to PATH' 选项")
            print()

        if not config_ok:
            print("2. 修复 MCP 配置:")
            print("   检查 mcp_config.json 文件格式是否正确")
            print("   参考 mcp_config.json.example 示例")
            print()

    print("=" * 70)

    # 平台特定提示
    if sys.platform == 'win32':
        print()
        print("💡 Windows 用户提示:")
        print("   - 安装 Node.js 后需要重启终端")
        print("   - 确保在 PowerShell 或 CMD 中运行，不要用 Git Bash")
        print("   - 如果仍有问题，尝试以管理员身份运行")


if __name__ == "__main__":
    main()
