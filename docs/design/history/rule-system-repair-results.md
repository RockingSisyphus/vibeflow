# Rule、Node 与插件完整修复验收

修复起点为 `15adf51`，历史基线为 `f169429`。27 个行为主题、119 个历史不匹配场景均已修复或按确认的接口决定迁移，全部验收通过；这些数量不表示独立根因数量。当前 1219 项基线对照和 205 项接口场景均通过，观察错误为 0。

## 对应关系

[修复计划](rule-system-repair-plan.md) 保留 R01–R27 与六个批次。[机器报告](../../maintainers/evidence/index.md#artifact-d561a82679d8256e) 记录每个主题的实际案例 ID、当前期待及观察、验收状态和批准迁移。R10 和 R19 按确认的分类删除、通用 Rule 入口迁移；R21 同时包含 Node shape 诊断修复与分类资源删除。其他主题恢复或补齐原健康审查目的。

机器报告引用的冻结参考保留修复前实际观察，当前期待不会改写它。当前案例保留原 ID，新增的合法对照与原错误可区分；源规则复用和调用关联仍有独立验证。

## 实现与迁移

Node 分类资源、默认继承和旧公开字段已删除，规则与展示直接归属完整 Node。领域示例通过参数化 tags 识别归属，自己声明浅蓝色；执行继续使用原生 Node/Nodeset/Loop。

Rule 实现使用独立语言和源码声明，不按业务平台选实现。raw/typed 结果共用状态、端口、记录类型和严重度校验；JS records 拒绝非 JSON 值，生命周期合法 void 行为保留。实现替换先确定有效定义，再生成默认参数和来源。

Python 相对导入、辅助目录和 JS dynamic/require 接入 Target 真实分析资料；默认主题与公开 leaf 共用指标。导入 Rule 限定自身闭包，planned helper 复用实际源码闭包。已加载未调用 Nodeset 只使用声明及真实可得事实，关闭审查保留原生身份。

默认健康规则恢复 Decision 路由输出、契约重叠、examples warning、公开 callable、安全内置 decorator 和模块 try/match 限制。Python 的 outputs 示例限制来自所选默认 Rule；JS 的合法输出示例可表达并通过。

BaseLib、Plugin、HostExtension 选择字段贯通声明和报告。独立 JS 扩展与 Python 已引用库/已选插件进入同一引擎，原生生命周期继续保留。报告和 Architecture 不再固定声明 trusted。规则预览保留实际资源作用域及来源，不执行 Rule 或业务代码。

用户声明迁移见 [迁移说明](../../../distribution/docs/user/rule-system-migration.md)。保留历史 ID；分类和平台字段按批准决定迁移，非法端口等反例仍检查完整正式诊断。未知 Ruleset 的已加载未调用声明不再被测试假定忽略。worker 状态反例改用声明阶段合法的冻结引用，使实际状态 Rule 得到执行，导入写入反例仍独立检查 marker。

## 历史参考与复现

`../../tests/fixtures/rule_parity/reference.json` 冻结旧基线和修复前观察。原始 [51 项对照差异](../../../tests/fixtures/rule_parity/RESULTS.md) 和 [68 项接口差异](../../../tests/fixtures/rule_gaps/RESULTS.md) 文档保留为历史记录。

```bash
npm_config_cache=/tmp/vibeflow-npm-cache python tests/fixtures/rule_parity/run_all.py --current-only
npm_config_cache=/tmp/vibeflow-npm-cache python tests/fixtures/rule_parity/run_all.py --baseline f169429
npm_config_cache=/tmp/vibeflow-npm-cache python tools/verify_project.py --full
python quality/test.py
```

完整门禁实际运行两组沙箱，空组、残缺记录、重复或丢失 ID、不匹配和进程错误都不能作为通过。用户程序的业务类型错误不扩充为健康规则；原生解析、绑定、ABI、编译和运行资料仍保持真实。

## 完整验收

2026年10月03日，以上两个最终命令均以退出码 0 完成。统一门禁全部 12 阶段通过，没有跳过浏览器或 SVG 验收。

| 验收 | 实际结果 |
|---|---|
| 仓库独立质量，开始及结束 | PASS，0 error / warning / info |
| Python 语法检查 | PASS |
| 全量回归 | 1576 passed，0 failed，0 skipped |
| Python 真实集成沙箱 | 138 passed，0 failed |
| JS 最小项目 AOT 与真实执行 | PASS |
| JS 集成与真实浏览器 | 67 passed，0 failed，0 skipped |
| 基线对照当前实现 | 1219 matched，0 unmatched，0 process errors |
| 新接口、组合与实际 SVG | 205 matched，0 unmatched，0 process errors |
| wheel 隔离安装与双 Target 入口 | PASS |
| 两个发行 profile、完整性、真实入口及解包 | PASS |
| 生成物清理及最终目录检查 | PASS，cleanup targets: 0 |
| 独立 quality/ 测试 | 46 tests OK |

完整工作目录为 `/tmp/vibeflow-repair-full6`，命令日志为 `/tmp/vibeflow-repair-full6.log`，独立质量测试日志为 `/tmp/vibeflow-repair-quality-tests-complete.log`。机器报告保存两组逐项观察、最终阶段结果和日志及冻结参考的 SHA-256。

本次完成边界是已登记主题及其保留、新增场景；有限案例不代表穷举任意第三方规则或所有语言程序。原生执行机制与命令范围保持原有职责，后续语言 Target、自动发现、热加载及自动修复不在本次范围内。
