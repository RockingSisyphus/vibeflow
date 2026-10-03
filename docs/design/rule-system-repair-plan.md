# Rule、Node 与插件系统修复及迁移

2026年10月03日确认。基线 `f169429`，修复起点 `15adf51`，目标版本 `0.15.0`。原审计有 1,219 项基线对照和 205 项新接口场景，119 项不匹配，按 27 个行为主题登记；它们不是 27 个已证明相互独立的根因。历史事实保留在原盘点及结果文档，不用新期待覆盖旧观察。

## 决定与边界

- 删除 category 及分类默认继承。完整 Node 自己声明 ID、契约、实现、规则与展示，config 通过 `type_used` 引用；保留自由 tags/metadata，不引入模板继承。
- Rule 使用独立的 `RuleImplementationDescriptor(language, source)`，不声明业务平台 targets。核心按执行语言族加载唯一实现，JS/TS 属于同族；业务目标资料交给规则自行解释。
- 默认 Python 导入 Rule 恢复模块级 try/match 的声明结构限制，需要放宽时替换规则。
- 审查负责代码及架构健康度，不替代编译器检查业务正确性。真实解析、绑定、原生计划仍必须获得实际成功事实。
- 保留原生 Node/Nodeset/Loop 自由组合和执行协议；不恢复 flow_kind 授权、trusted/external 豁免、policy hooks 或第二套诊断。
- 保持命令范围和完整 workspace 解析上下文；不增加孤立源码扫描、项目启用或持久检查资格。
- Rule ABI v1、Plugin ABI v2、Workflow ABI v4 不变。声明一次迁移，不保留长期桥接。

## 六批实施

1. 声明：删除 category；独立 Rule 实现；严格端口、semantics、展示类型；examples.outputs 由语言默认规则判断。
2. 执行：完整验证 raw/typed 结果；严格 JS records；合法 finding 不取消有效 records；替换默认值与来源一致。
3. 分析：共享 Target 指标与已解析导入关系；自定义辅助目录、相对导入、literal dynamic/require；公开 implementation leaf 正式接入。
4. 规则：恢复声明、接口、examples、public callable、安全 decorator 和模块结构的默认健康判断。
5. 范围：实际导入闭包、planned helper、独立原生身份、已加载未调用定义、独立 Plugin/Host 规则选择。
6. 正式入口：统一实际资源作用域、冲突和位置运输、预览、报告、图形与完整验证。

## 问题与验收对应

| ID | 主题 | 原不匹配数 | 批次 | 验收/处理 | 结果 |
|---|---|---:|---:|---|---|
| R01 | Decision 缺 route 输出 | 1 | 4 | 默认声明 Rule 与合法路由对照 | 通过 |
| R02 | requires/provides 重叠 | 1 | 4 | 默认契约 Rule，可明确替换 | 通过 |
| R03 | examples 形状警告 | 3 | 4 | 恢复字段、映射和 warning | 通过 |
| R04 | Python 相对 BaseLib 链 | 2 | 3 | 实际最长链和阈值 | 通过 |
| R05 | 自定义辅助目录函数数 | 1 | 3 | 已允许目录实际指标 | 通过 |
| R06 | 子 Nodeset [] 身份 | 2 | 5 | 空审查不取消原生身份 | 通过 |
| R07 | 已加载未调用 Nodeset | 3 | 5 | 声明检查，无伪造调用 | 通过 |
| R08 | 独立 JS Plugin/Host | 28 | 5/6 | 正式 import/static 与生命周期对照 | 通过 |
| R09 | JS examples.outputs | 2 | 1/4 | 声明可表示，JS 默认规则接受 | 通过 |
| R10 | category 可选差异 | 1 | 1 | 批准移除，完整 Node 直接声明 | 批准迁移，通过 |
| R11 | semantics 数字字符串化 | 2 | 1 | 正式类型诊断，不自动转换 | 通过 |
| R12 | public lambda | 1 | 4 | callable 检查与普通值对照 | 通过 |
| R13 | 合法内置 decorator | 2 | 4 | 绑定身份、别名与遮蔽 | 通过 |
| R14 | 空 try/match | 2 | 4 | 恢复默认结构限制，写入仍阻断 | 通过 |
| R15 | 邻居 Node 导入检查越界 | 1 | 5 | 自身闭包和 [] 隔离 | 通过 |
| R16 | planned helper 初始化 | 1 | 5 | 旧新局限；默认 planned Rule 检查真实闭包 | 通过 |
| R17 | JS 非 JSON records 改写 | 3 | 2 | provider failed、consumer 不执行 | 通过 |
| R18 | JS dynamic/require 资料 | 2 | 3 | 精确边、位置、可达与使用归属 | 通过 |
| R19 | JS 平台 Rule 中立检查 | 3 | 1/6 | 批准通用入口，旧平台字段明确迁移 | 批准迁移，通过 |
| R20 | bundle 冲突来源运输 | 5 | 6 | 五种资源双方来源 | 通过 |
| R21 | category/Node 对象 shape | 8 | 1/6 | Node 类型诊断；分类资源明确移除 | 修复及批准迁移，通过 |
| R22 | Rule 非字符串端口 | 16 | 1 | 声明阶段拒绝，无 handler 执行 | 通过 |
| R23 | mixed Target 预览合并 | 2 | 6 | 预览与正式实际作用域相同 | 通过 |
| R24 | 同 Target 预览冲突来源 | 1 | 6 | 保留双方来源 | 通过 |
| R25 | 替换参数来源 | 8 | 2 | 替代 defaults、新字段、显式与覆盖 | 通过 |
| R26 | 公开 implementation leaf | 12 | 3 | 两 Target 真实正常/超限源码 | 通过 |
| R27 | 非法 finding severity | 6 | 2 | raw/typed/Python/JS 状态与依赖 | 通过 |

最终 12 阶段门禁及独立质量测试全部通过，逐项观察、案例 ID 和迁移原因见 [修复验收](rule-system-repair-results.md) 及其机器报告。

## 一次迁移

- category 默认 rulesets/presentation 展开到 Node；领域示例改用参数化 tags 约定，Node 自己声明浅蓝色。
- Rule 实现删除 targets/completion，只声明 language/source；不同业务平台逻辑由统一 check、helper 或多 Rule 组合承担。
- BaseLib、Plugin、HostExtension 明确选择默认 Ruleset；空列表如实表示未选审查。
- Python 默认接口规则仍禁止 outputs 示例；中立声明允许表达它，JS 默认规则接受它。
- 变更当前夹具时保留历史观察和案例 ID，并登记批准变化。分类资源负例转为明确移除诊断，另保留 Node 样式正反例；不以提前崩溃冒充规则拒绝。

## 验证与完成条件

每批跑相关真实沙箱；全量以现有案例加迁移正反例为底座。新增用例包括通用 Rule 入口、重复执行族、Node 直接展示、健康审查边界、Source API、provider/consumer 和实际 marker、planned helper、未调用定义及跨 root。

完整验证接入两组真实沙箱。冻结基线与修复前观察作为参考，日常执行 current-only，保留显式重跑 f169429 的入口。任何不匹配或观察错误使命令失败。

```bash
npm_config_cache=/tmp/vibeflow-npm-cache python tools/verify_project.py --full
python quality/test.py
```

完整验证包括全量回归、Python/JS 沙箱、既有真实浏览器验收、wheel、两个发行 profile 和发行入口。独立 quality/ 保持标准库且不导入内核。最终更新问题表和机器报告；中间提交不作为完成版本发布。
