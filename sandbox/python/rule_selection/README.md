# 规则选择综合案例

同一个嵌套工作流使用三份配置，通过真实 SDK、Plugin 和 `vibeflow validate --json` 验证规则选择。案例不增加 Node 类型默认规则测试；所有叶 Node 的类型默认选择都是 `[]`。

```text
Workflow：静态默认 B / 动态整体 D / 显式 []
├─ direct：直接引用局部 Rule A
├─ disabled：局部选择 []
├─ left → inherited：继承上级，内部 local 使用 Ruleset A
├─ right → inherited：同一定义的另一个实际调用位置
├─ takeover：显式选择图 Ruleset C，内部 local 使用 A
└─ muted：显式图选择 []，内部 local 仍使用 A
```

每张图都由 start/end 和顺序连接组成。完整配置见 [默认](project/configs/default.jsonc)、[动态](project/configs/dynamic.jsonc)、[空选择](project/configs/empty.jsonc)。`inherited`、`takeover`、`muted` 的内部图相同，只有图规则选择不同。

| 配置 | 预期图级执行 | 检查范围 |
| --- | --- | --- |
| default：省略 Workflow rulesets | B 三次，C 一次 | B 分别负责根、left、right；C 负责 takeover |
| dynamic：Workflow 选择 D | D 一次，C 一次 | D 负责根、left、right；C 负责 takeover；B 不执行 |
| empty：Workflow 选择 [] | C 一次 | left/right 不继承规则；takeover 的 C 仍执行；B/D 不执行 |

三份配置中，局部 A 都检查 direct、left.local、right.local、takeover.local、muted.local 五个位置，disabled 不执行局部规则。因而可以实际观察图级 C+A、图级取消后仍保留 A，以及重复调用独立归属。

B 是 Plugin 贡献的 `workflow_default` Ruleset，B/C 使用 `current_graph`，D 使用 `effective_subtree`。每个图 Ruleset 都有 analyze → check 的 `requires/bindings` 依赖：分析输出 typed coverage Record，检查消费同范围结果。check 输出 `SELECTION.GRAPH` warning，记录选择标识、范围入口、负责图路径、图内调用及全局背景。局部 A 输出 `SELECTION.LOCAL` warning，记录调用位置，并检查公开 facts 没有 graph/global_graph/node_catalog/catalogs。warning 是本案例用于核对执行的可见证据。

默认遍历不进入 takeover/muted 内部，但父图仍能看到两个子图调用；负责范围外的背景也可读取。runner 使用路径多重集合断言次数，不能用合并后的集合掩盖重复执行。它还断言默认 B 被动态 D 完整替代。

直接 Rule 引用在 import 与 static 阶段执行，故 direct 有两条阶段不同的证据；Ruleset A/B/C/D 明确只选择 static 入口。runner 分阶段断言，不把不同阶段当作重复扫描。

## 运行

```bash
python sandbox/python/rule_selection/run_all.py
python sandbox/python/rule_selection/run_all.py --work-dir /tmp/vibeflow-python-selection
```

runner 在临时副本执行，不修改案例源码。指定工作目录时保留三个 `*-health.json` 与 `report.json`；工作目录应使用新的空目录。两个 Target 的 integration runner 已登记此案例，完整仓库验证也会执行。共享断言见 [runner 支持模块](../../../tests/fixtures/support/rule_selection.py)。

## 目录用途与边界

仅用于：python / rule_selection 案例，验证显式 Rule 选择、覆盖及执行记录；保留真实项目输入与 runner。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../docs/maintainers/directory-layout.md)。
