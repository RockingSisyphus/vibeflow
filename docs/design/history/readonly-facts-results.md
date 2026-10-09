# RuleContext 共享对象图修复

本轮从开发者报告的 0.15.0 内核及当前源码复现只读转换的共享引用丢失。原始发行内核 SHA256 为 `e3a964f1804e01eb7a9d4b121cd53b7393d662347a77b3cbeb9f6618130d5095`；运行环境为 Python 3.13.13。

## 复现与改动

每层只有一个不同 tuple、两个位置共用上一层对象的输入，在 12 层转换后生成 4095 个不同 tuple。共享 list 和混合容器也丢失身份；mapping、dataclass 及普通服务对象对照没有同样的展开。嵌套只读保护和原输入修改后的隔离在修复前已有效。

`readonly` 对 tuple/list 和 set/frozenset 的完整转换结果登记 memo，后续引用复用该结果。通过 mapping/dataclass 回到正在转换的序列时，保留递归中已完成的实例。一个 RuleContext 的 facts、subject、scope 共用本次转换 memo；不同上下文仍分别生成快照，不引入跨运行缓存。

补齐转换缓存后，原 MNIST 配置的一次 120 秒有界审查仍未返回。后续采样确认内置 Python 动态调用分析重复复制 AST，并重复线性查找源码引用。该 Target 内部的只读分析改用已解析的 `_tree/_node`，并为本次分析建立调用和符号索引，保留原来的首个匹配语义。公开 AST getter 继续提供隔离副本，规则判断、阈值和执行协议沿用原有机制。

## 验证范围

| 验证 | 结果 |
| --- | --- |
| tuple 共享图 12 层 | 不同输出 tuple 从 4095 降为 12 |
| tuple 共享图 64 层 | 64 个不同 tuple，每个输入对象只遍历一次 |
| 混合 mapping/list/tuple/set/frozenset | 共享身份、只读性、原输入修改隔离均符合预期 |
| mapping/dataclass 间接回引用 | 保持单一快照身份；原有 dataclass 循环回归保留 |
| 内置动态调用分析 | 不调用公开复制 getter，分析前后原始 AST 相同；公开树副本仍可独立修改 |
| 相关 Core、Python、JS、SDK 默认值、运行观测、规则正式入口回归 | 188 passed |
| 仓库独立质量 | 0 error / 0 warning |
| 原 MNIST 配置，源码内核 | 约 117 秒返回完整 JSON；FAIL，52 errors / 91 warnings |
| 原 MNIST 配置，重建发行内核 | 约 114 秒返回完整 JSON；FAIL，52 errors / 91 warnings，与源码结果一致 |

MNIST 的完整诊断包含大小限制、导入、副作用、契约及自定义规则执行等问题，尚未逐项判定为业务问题或内核误报。其中 `vibetrain.model_structure.check` 报 `cannot pickle 'mappingproxy' object`；业务插件 `_model_structure_support.merge_params` 使用 deepcopy 处理冻结资料。本轮没有修改 VibeTrain 的源码、配置或安装内核，也没有执行训练。

源码修复验证和重建发行包的观察保存在 `tests/fixtures/python/readonly_graph`。`before.json/released-before.json` 为修复前参考，`after.json/released-after.json` 为修复后最小复现与对照；`verification.json` 记录最终发行哈希和真实工作流复查，`mnist-report.json` 保存发行内核的完整报告。补充的动态调用和文档回归为 20 passed，独立质量工具为 46 tests passed。两个 profile 的发行内核字节相同，正式启动器完整性检查通过；没有重跑完整仓库门禁。完整报告的退出码、状态与错误数量独立记录，不把观察完成当作项目通过。
