# 第二轮补测结果

本文冻结修复前的历史事实。当前修复与验收见 [完整修复结果](../../../docs/design/history/rule-system-repair-results.md)，当前期待及实际观察见 [机器报告](../../../docs/maintainers/evidence/index.md#artifact-d561a82679d8256e)。

2026年10月03日。生产代码仍为 `15adf51d0676`，本轮新增测试和覆盖说明，未修生产实现。

完整运行方法见 [README](README.md)。五组共 205 个持久场景；137 项符合期待，68 项不匹配，观察进程错误为 0。退出码为 `1`，失败保持可见，没有 `xfail` 或降低验收条件。

| 组 | 场景 | 匹配 | 不匹配 |
| --- | ---: | ---: | ---: |
| Python 导入与 helper 边界 | 11 | 9 | 2 |
| JS records、Source API、平台与 bundle | 37 | 24 | 13 |
| 规则图、缓存、finding 与公开 leaf | 81 | 55 | 26 |
| 声明类型与跨 root/Target | 56 | 29 | 27 |
| 领域 Node 原生组合与图形 | 20 | 20 | 0 |
| 合计 | 205 | 137 | 68 |

匹配包括正确拒绝的负例。68 项是不同场景的不匹配数量，同一问题可触发多项，不表示发现了 68 个独立根因。它们与此前 51 项对照不匹配属于不同用例集合。

## 不匹配分组

| 问题 | 场景数 | 实际观察 |
| --- | ---: | --- |
| Python 选中邻居的导入规则越界 | 1 | 无导入边的明确空选择 Node 被邻居的规则拒绝，并归给错误调用 |
| planned stub helper 初始化的既有局限 | 1 | 主文件安全，实际 helper 顶层 marker 仍写入并完成业务；属于旧新共有局限 |
| JS 非 JSON typed records | 3 | Map/Date/undefined 被改写成 `{}`/`{}`/`null`，provider completed，consumer 执行 |
| JS dynamic/require 导入资料 | 2 | snapshot 含 helper，公开导入边/精确位置/可达和使用归属却缺失 |
| JS 双平台实现的中立检查 | 3 | 两平台 build 和数值产物均合法；validate/quality/review 错误拒绝，consumer 未执行 |
| Bundle 原生资源冲突来源运输 | 5 | 五组均按 DESCRIPTOR.CONFLICT/exit 1 正确拒绝且无产物，但正式错误丢失冲突双方路径 |
| category/Node 对象 shape | 8 | 预览抛异常而非单个 JSON 诊断；validate 的资源诊断或位置也不完整 |
| Rule 非字符串输入/输出类型 | 16 | 数字/对象被转为字符串接受；正常真实 handler 执行，声明阶段未拒绝 |
| mixed Target 的规则预览 | 2 | validate 合法，review-rules 错误合并不同语言的同 ID 资源 |
| 同 Target 冲突预览的来源 | 1 | validate 保留双方来源，review-rules 的正式 JSON 只保留冲突原因 |
| 替换规则参数来源 | 8 | 实际参数值和新增默认值正确，validate 有效计划与预览中的默认来源仍错误/缺失 |
| 公开 implementation leaf 正式接入 | 12 | 正常和超限源码都未得到所需真实 metrics/chain 或 JS handler；maintainability 同源码对照全部符合期待 |
| finding 非法 fatal/None severity | 6 | Core raw/typed、Python/JS 均未使 provider failed，consumer 仍消费记录；Python 聚合拒绝也不能代替正确执行契约 |

后两种来源丢失由本轮正式负例额外暴露：Bundle 的冲突来源在加载器中存在，正式 build 输出丢失；同 Target Rule 冲突的 validate 与预览也不一致。拒绝正确并不意味着错误报告完整。

## 已取得的正常与拒绝证据

- 8 个领域组合正例实际执行：两个 Target 的分支左路 `7`、右路 `10`，Nodeset 和单次 Loop 均为 `7`。分支以最小 Nodeset 包裹同一模型 Node，并由纯 rekey Node 真实产生各分支独有输出键，再由 `optional_one`/`any_active` 合流；没有修改原生输出键或数据交付规则。
- 12 个领域负例在正式 validate 和 run/build 阻断；模型标记缺失或变换 helper 中非法定义的 Rule ID、文件/行号及 `left/model`、`right/model`、`stage/model`、`loop/model` 关联都符合期待。
- 8 个正例实际生成 Architecture、Mermaid、SVG。检查具体模型节点的 SVG 几何填充色为 `#cceeff`：分支两个，其余一个；不是只搜索样式表中的颜色字符串。
- Bundle 的五组正常资源只通过 bundle 接入，实际值 `7`，Host/Capability/Runtime Plugin 的创建、运行和清理顺序正确。悬空引用逐组报告实际缺失文件，父目录真实存在，不由更早的目录错误冒充。
- 12 个源码缓存场景全部符合期待：同值复用，不同 typed inputs/有效参数分别执行；每个新 session 重跑，实际 proof 正确，正式 findings 保留 `first/second` 两个调用关联，源码规则看不到某个单独调用的事实。
- 合法 error/warning/info findings 的 provider completed，requires consumer 真实消费 `3`；数字/字符串假 finding 形成 RULE.EXECUTION，provider failed，consumer unavailable 且未执行。Core 同时检查 raw 和 typed 返回形状。合法 error finding 不应使已有记录失去可用性。
- 显式 includes 好/坏选择及 INPUT.CONFLICT、INPUT.UNBOUND、PARAMS.SCHEMA 都触达目标分支并保留资源位置。预览没有执行 Rule 或业务实现。
- 合法数组、空列表、null、对象、async records 真实到达 consumer；NaN、Infinity、bigint、循环值及不存在源码的查询被正式拒绝，没有伪造成功资料。
- 分类/Node 的合法 shape 与非法 list 已有正式拒绝对照；同 Target 兄弟 root 的合法引用和混合语言 validate 均成立。中立平台测试要求实际检查发生，不规定未来合法实现必须执行一次还是分别检查两平台。

## 验证及边界

统一执行保存项目副本、stdout/stderr、handler 事件、编译产物和实际图形：

```bash
python tests/fixtures/rule_gaps/run_all.py \
  --work /tmp/vibeflow-rule-gaps-complete \
  --report /tmp/vibeflow-rule-gaps-complete.json \
  --toolchain /tmp/vibeflow-rule-parity-final/javascript-toolchain/baseline \
  --renderer /tmp/gsko-vibeflow-0142-20261002-8hA6MC/kernel/tools/mermaid-renderer
```

复用目录的两个锁文件与当前仓库逐字节一致；可按 README 不带复用参数重新安装。正式 CLI 缺少完整执行状态时，同项目另用公开 JS Target API 的独立进程取状态，保留第一次 CLI 诊断/退出码和 consumer marker，未用 probe 结果替换命令结果。

报告机制测试 30 passed；仓库独立质量 `--profile all` 为 PASS，`repo_check/test.py` 45 tests OK，语法与 `git diff --check` 通过。报告机制测试不代表 68 项已修复。浏览器目标的纯数值产物在 Node 中执行，实际浏览器功能仍由原浏览器沙箱验收。

此前的 1,219 项基线对照及 51 项不匹配保持 [原记录](../rule_parity/RESULTS.md)，不会把新接口用例当成旧版已有能力，也不会把当前红例当作已修复。

本轮不重跑完整发行门禁或 1,219 项全组，不修改生产源码、规则期待和扫描范围。新增的覆盖限于第二轮报告及其有限对照，不声称穷举任意插件或所有非法值。
