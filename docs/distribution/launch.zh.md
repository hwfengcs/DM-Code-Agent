# 待发布稿：读到一行正常 Python，我的 Agent 为什么开始“抢修”？

状态：稿件已准备，尚未对外发布。根据社区规则调整篇幅，保留维护者身份说明。

---

这行正常 Python，曾让我的编程 Agent 误以为工具失败：

```python
from errors import NotFound
```

文件存在，读取也成功。问题出在观察结果分类器：它扫描工具输出全文，只要遇到 `error`
等标记就判断失败。工具读回来的源码，被当成了工具自己的状态。

后来我给编辑工具加了“修改后源码回显”，这个老问题反而更明显了——更多的源码进入观察，
也带回更多可能误触发的文本。

一次历史分析检查了 30 份 trace：84 次被标记的工具失败中，有 38 次误报。
对同一批观察重新分类后，这 38 次误报消失，原先识别出的 46 次真失败仍被保留。
这个结果只支持这批观察上的分类改进，不能直接解释为 Agent 总体成功率提高。

我维护的 [DM-Code-Agent](https://github.com/hwfengcs/DM-Code-Agent) 把工具调用、修改、失败和测试记录下来，
用来查这种“最终回答里看不出来”的问题。修复时按来源区分工具状态和搬运内容，执行工具优先使用退出码，
未知扩展工具保留保守兜底。

[完整文章](https://github.com/hwfengcs/DM-Code-Agent/blob/main/docs/articles/02-error-is-not-failure.zh.md)
包含最小复现和原始证据。也可以直接打开[浏览器演示](https://hwfengcs.github.io/DM-Code-Agent/)：
两次运行做了相同修改，都说完成了，只有一次运行测试。报告能让你自己检查这个差异。

演示里的助手决策来自脚本，文件修改和 unittest 确实执行，不需要模型 key。
真实使用时，项目还能导出无需服务器即可打开的单文件 HTML 报告。

如果你也碰到过 Agent 宣布完成、实际却遗漏检查的情况，欢迎提供可复现的问题。
[中文上手指南](https://github.com/hwfengcs/DM-Code-Agent/blob/main/docs/getting-started.md)
介绍了安装、运行和报告检查流程。

## 短文案

读到 `from errors import NotFound`，我的 Agent 竟然开始错误恢复。
工具没有失败，分类器把源码里的单词当成了失败状态。

我把排查过程和复现整理进 DM-Code-Agent，也做了无需 key 的交互演示：
两次运行都宣布完成，只有一次留下测试证据。

演示：https://hwfengcs.github.io/DM-Code-Agent/

源码与文章：https://github.com/hwfengcs/DM-Code-Agent
