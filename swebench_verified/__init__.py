"""SWE-bench Verified 评测子系统。

**独立于 `dm_agent/`**：不往内核加任何依赖、开关或代码路径。CLAUDE.md 的约定是
"要复活就写成外部扩展或独立子系统"，这里选了后者——它有自己的 venv、自己的
数据缓存，主项目的 `uv.lock` 一行都不变。

devlog 33 删掉 SWE-bench Lite 子系统的理由是 Tier-1 resolved 0.0%、Tier-2
verifier 从未实现。这次不再自己写 verifier：判分完全交给官方 harness，
我们只负责产出 predictions.jsonl。
"""
