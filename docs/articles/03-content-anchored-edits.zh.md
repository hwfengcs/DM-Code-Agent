# 内容锚定编辑如何减少相邻代码误伤

[English](03-content-anchored-edits.en.md) · [文章目录](README.md) · [交互演示](https://hwfengcs.github.io/DM-Code-Agent/)

Agent 想改一条赋值语句，选中的行号区间却多了一行。编辑成功了，相邻变量的定义也消失了。Python 语法仍然合法，直到运行代码才暴露问题。

DM-Code-Agent 的历史 trace 里，这种失败消耗了许多看起来像“推理不够”的步骤。修改编辑接口提供了更直接的干预。

## 刚读过文件，也可能选错区间

最初的解释把问题归因于过期行号。检查后发现，read-before-edit 守卫已经会拦截过期读取。剩下的问题是：模型即使看到最新行号，仍可能选错区间；旧回执只说替换了哪些行，没有显示修改后的代码。

2026 年 8 月 4 日的修改同时包含三项：

1. 优先使用 `old_string` / `new_string`。原文必须逐字匹配且唯一命中，包括空白；零处或多处命中都不修改文件。
2. 返回带新行号与上下文的编辑结果。
3. 对修改后的 Python 做语法检查并报告问题。这是反馈，不是回滚，也不是程序正确性证明。

原文和替换内容依然由模型选择。唯一匹配降低的是定位风险，不能保证它选对了原文，或写对了新逻辑。

## 最小隔离复现

安装[项目](../../README_ZH.md)后，执行下面的 Python 代码。它只使用临时目录和真实编辑函数：

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from dm_agent.tools.file_tools import edit_file

with TemporaryDirectory() as directory:
    path = Path(directory) / "example.py"
    source = "limit = 3\nlabel = 'keep me'\n"
    path.write_text(source, encoding="utf-8")
    edit_file({"path": str(path), "old_string": "limit = 3",
               "new_string": "limit = 4"})
    assert path.read_text(encoding="utf-8") == "limit = 4\nlabel = 'keep me'\n"

    path.write_text(source + source, encoding="utf-8")
    before = path.read_bytes()
    edit_file({"path": str(path), "old_string": "limit = 3",
               "new_string": "limit = 4"})
    assert path.read_bytes() == before  # Ambiguous match: no write.
    edit_file({"path": str(path), "old_string": "limit = 99",
               "new_string": "limit = 4"})
    assert path.read_bytes() == before  # Missing match: no write.
print("Unique replacement succeeded; ambiguous and missing matches changed nothing.")
```

它验证的是工具的定位约定，不模拟模型能力、Agent 的读取守卫或真实修复是否正确。

## 历史运行观察到了什么？

基线和修改后的工具跑同一组 30 题，使用 `deepseek-chat`，模型设置、允许文件策略和判分方式相同。每个配置只跑一轮。干预同时包含实现和工具描述变化，因此不能分离每一项的独立作用。

| 指标 | 基线 | 修改后 |
| --- | ---: | ---: |
| trace 中识别的编辑自伤 | 13 次 / 6 题 | 0 次 / 0 题 |
| `edit_file` 调用 | 63 | 47 |
| 使用 `old_string` 的调用 | 0 | 47 |
| `old_string` 未命中 | 不适用 | 0 |
| 总步数 | 350 | 325 |
| 估算 token | 1,458,155 | 1,401,267 |
| 通过任务 | 22/30 | 25/30 |

“自伤”来自历史 trace 审阅，包括 Agent 识别到自身编辑出错的步骤。它为这批样本中的具体机制提供证据，不能保证将来零误伤。通过数变化中包含 5 题修好和 2 题回归，不能独立证明模型总体成功率得到提升。

修改后这轮没有命中过语法检查，所以它也没有为语法检查的收益提供直接证据。语法检查本来就不能识别所有原始问题：删掉一个必要的赋值，代码仍可能有合法语法。

## 一个改进暴露了另一个缺陷

回显更多代码，也让全文搜索 `error` 的观察分类器更容易误判。replan 从 58 次升到 78 次，原始审阅将其中 17 次归于编辑回显。包含 `from errors import NotFound` 的成功编辑，可能被判成失败。

这笔成本应与收益一起呈现。这一轮估算 token 仍减少 3.9%，步数减少 7.1%，但反馈链路还需要继续修复。[下一篇文章](02-error-is-not-failure.zh.md)解释了为什么必须区分工具状态与搬运的源码。

离线比较保存的判分结果，不调用模型：

```bash
python -m dm_agent.benchmarks.score_diff bench_reports/ablation-scope-20260804.json bench_reports/editfix-20260804.json
```

在仓库根目录运行，因为存在回归，退出码 1 是预期结果。它比较的是存档结果，不会重现当年的模型运行。

## 原始证据

- [完整排查、机制修正与代价：devlog 38](../research-log/38-edit-file-precision.md)
- [基线报告](../../bench_reports/ablation-scope-20260804.json)与[修改后报告](../../bench_reports/editfix-20260804.json)
- [当前编辑实现](../../dm_agent/tools/file_tools.py)
- [失败分类后续修复：devlog 39](../research-log/39-observation-failure-classification.md)

[DM-Code-Agent](../../README_ZH.md)让这些工具交互过程可以被检查。可以先试[无需 key 的演示](../getting-started.md)，一起查看内容锚定编辑、测试证据和导出的报告。
