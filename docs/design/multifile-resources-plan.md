# 多文件资源与统一展示

起点：`3ee7396`；版本 `0.15.0`，Plugin ABI v3 / Rule ABI v1 / Workflow ABI v4。

四类资源通过选中插件接入，共用显式 `implementation_files`、源码归属、Ruleset 和 `presentation`。Host 保持一个实例；`dependencies` 仍表示宿主实例依赖，纯库通过 `base_libs` 引用。插件的 `declaration_rulesets` 审查声明，`rulesets` 审查 compiler/runtime。

实施顺序：公共声明和 SDK → 源码与默认规则 → 绑定及 AOT → 正式展开 SVG 与 Architecture → 沙箱、文档和发行。

正式展开图增加实现文件和真实依赖，Architecture JSONC 保存同一资料以及样式来源。每个文件沿用现有默认大小限制；不增加资源累计行数上限。未选择规则如实显示未约束。

新增至少 240 个真实 CLI 场景：注册 40、源码归属 48、规则 32、修改 32、展示 64、运行 24。图形验证包含 JSONC、Mermaid、浏览器中的最终 SVG 计算样式与几何。修改案例重新检查、运行和渲染。

保留既有历史案例及 ID。最终执行 `npm_config_cache=/tmp/vibeflow-npm-cache python tools/verify_project.py --full` 和 `python quality/test.py`，覆盖浏览器、wheel、发行 profile 和真实发行入口。通用 Host 沙箱不替代 GSKO 生产验收。
