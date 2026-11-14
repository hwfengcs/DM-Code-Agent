# 为什么源码里的 error 会让 Agent 触发重规划？

[English](02-error-is-not-failure.en.md) · [文章目录](README.md) · [交互演示](https://hwfengcs.github.io/DM-Code-Agent/)

读取下面这行合法 Python 代码，曾经会让 DM-Code-Agent 进入失败恢复：

```python
from errors import NotFound
```

文件存在，读取也成功了。问题在观察结果分类器：它对工具输出全文匹配失败标记，其中包括裸子串 `error`。

## 工具状态和搬运内容混在一起

同一条观察可能包含工具自身的状态，例如“文件不存在”；也可能包含工具搬运的内容，例如源码和子进程 stdout。把两者都当作状态扫描，就会让内容里的词语决定控制流程。

编辑工具加入修改后回显后，这个问题变得更明显。更完整的编辑反馈带回了更多源码，从而更频繁地触发既有分类缺陷。

2026 年 8 月 5 日的历史分析复查了同一批 30 份 trace：296 次工具调用中，旧判定标出 84 次失败，其中 38 次是误报。

| 误判来源 | 次数 |
| --- | ---: |
| 编辑回显中的源码 | 18 |
| `read_file` 正文 | 12 |
| `run_python` 打印 `ERROR:`，但退出码为 0 | 6 |
| 目录列表 | 1 |
| 测试输出 | 1 |
| 合计 | 38 |

如果按重规划事件统计，则是 **78 次 replan 中有 34 次误触发（43.6%）**。两种口径的分母不同。上一轮编辑实验统计的 17 次，仅指“编辑回显触发的 replan”，也不是全部误报。

## 最小复现

安装[项目](../../README_ZH.md)后运行下面的 Python 代码。它直接调用当前分类器，不需要模型，也不访问网络：

```python
from dm_agent.core.observation import is_failure_observation

source = "1 | from errors import NotFound"
assert "error" in source.lower()  # The old substring rule fires.
assert not is_failure_observation(source, action="read_file")

output = "stdout:\nERROR: expected fixture text\nreturncode: 0"
assert not is_failure_observation(output, action="run_python")
assert is_failure_observation("returncode: 2", action="run_python")
assert is_failure_observation(
    "Tool execution failed: permission denied", action="read_file"
)
print("Source text is not tool status.")
```

修复按来源区分证据。内核异常在观察开头识别；内置文件工具在已知的拒绝或状态位置判断，不扫描搬运回来的文件正文；执行工具以报告的退出码为准，因为成功命令也可能有意打印 `ERROR:`。编辑后语法检查不通过，仍然属于失败信号。

未知扩展工具仍保留较保守的文本标记兜底，因为无法保证其输出格式。这次修改没有把所有工具都改成结构化响应，也不能消除任意输出格式中的歧义。

## 先单独验证分类器，再讨论 Agent 总体效果

对同一批历史观察重新分类，38 次误报归零，原先识别到的 46 次真失败全部保留，另发现 4 次旧判定漏掉的失败。这直接支持“分类器在这批数据上改好了”，不能推广为任意仓库零误报。

后续一次真实运行的 replan 从 78 次降到 23 次，但同期还改了 linter 处理和 Windows 换行行为，无法单独归因于分类器。离线比较回答了更窄、也更明确的问题：对于已经观察到的这些工具输出，状态判断是否更准确？

可迁移的做法是：尽量让状态和内容分别传递。如果兼容性要求继续使用文本观察，就按产出工具的约定和状态位置判断。源码、引用示例和命令正文首先是内容，除非明确的状态信号说明失败。

## 原始证据

- [完整分析与统计口径：devlog 39](../research-log/39-observation-failure-classification.md)
- [此前记录的回显副作用：devlog 38](../research-log/38-edit-file-precision.md)
- [当前分类器](../../dm_agent/core/observation.py)与[行为测试](../../tests/test_observation_failure.py)
- [被审阅那轮的运行报告](../../bench_reports/editfix-20260804.json)

[DM-Code-Agent](../../README_ZH.md)保留了可供离线排查的工具观察。可以先试[无需 key 的演示](../getting-started.md)，查看失败、恢复与验证证据。
