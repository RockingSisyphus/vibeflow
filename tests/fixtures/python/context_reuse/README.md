# 规则上下文派生与资料复用

```bash
python -B tests/fixtures/python/context_reuse/probe.py \
  --report /tmp/vf-context-reuse.json
PYTHONPATH=src:. python -B -m tests.fixtures.python.context_reuse.cli_probe \
  --work /tmp/vf-context-reuse-cli --report /tmp/vf-context-reuse-cli.json
```

CLI 案例使用公开 SDK 定义 12 种 Node 和调用级、源码级两条 Rule，通过正式 validate 执行 24 次检查。每个 Node 使用唯一输出键，原生路由与契约不变。规则记录实际源码服务与 Node catalog 的身份，并检查调用级资料只提供给调用规则。规则自己的统计代码是受信扩展实现，fixture 明确选择身份检查规则，不依赖业务 Node 的副作用授权。

修复仅复用当前上下文已经生成的只读快照及其直接字段。新 subject、facts、scope 仍递归冻结；任意外部浅层 mappingproxy 不被当作完成冻结的资料。独立新上下文、原始资料重新提交以及各命令的检查范围保持各自语义，不添加跨检查的持久缓存。Python Target 在每次规则阶段建立共享事实上下文，加载状态仍按实际阶段刷新；JS Target 切换入口时派生已有上下文。

`tests/core/test_rule_context_reuse.py` 检查派生、外部代理、原始资料变化、临时对象身份复用、调用与源码边界；`tests/targets/python/test_context_reuse.py` 执行正式 CLI 案例。之前的 tuple DAG、混合容器、循环、只读及默认值隔离回归继续保留。

当前 Rule v2 的 Node 上下文只包含当前声明与局部源码，历史全量 catalog 身份断言已迁移。CLI 仍执行 24 次检查，同一个 Node 的两条规则共享局部源码视图，12 个 Node 各有独立的视图与声明；同时断言视图中没有其他 Node 或 catalog。

## 目录用途与边界

仅用于：context_reuse 专项实现回归的固定输入、预期及 runner；只保留有当前加载方的材料，运行产物写入临时工作区。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../../docs/maintainers/directory-layout.md)。
