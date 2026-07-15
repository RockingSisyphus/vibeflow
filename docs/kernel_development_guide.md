# VibeFlow 开发者工作流

本文档面向维护 VibeFlow（包名 `vibeflow`）自身的开发者，不是面向业务项目编写 node、nodeset 或 plugin 的使用者指南。

## 基本验证流程

修改 VibeFlow 代码后，默认运行以下命令：

```bash
PYTHONPATH=src python3 -m pytest tests/unit -q
python3 -m compileall -q src tests examples
PYTHONPATH=src python3 examples/integration_sandbox/run_all.py
PYTHONPATH=src python3 -m vibeflow quality-check --path .
```

其中最后一条是通用代码质量自检。它不再有仓库专属的 `--self` 模式；检查 VibeFlow 仓库自身时统一传入当前仓库路径 `.`。

验收标准：

- `quality-check` 必须输出 `PASS`。
- `errors` 必须为 `0`。
- `warnings` 必须为 `0`。
- 若新增代码触发 warning，优先重构新增代码；不要为了通过检查而随意放宽通用质量规则。

阅读 `quality-check` 结果时，先看每条 finding 的 `object_type:object_id` 和 source location，再看 `details`。文本输出会打印紧凑 `details:` 行；JSON 输出保留完整结构。重复函数、依赖环、双向依赖、跨目录/内部模块 import 等 warning 会在 details 中列出具体函数、import site、source/target module 和建议 public entry，优先改这些位置。

## `review` 编排契约

正式架构审核由统一命令编排，发布包入口和内核入口分别是：

```bash
python run.py review --config project/configs/main.jsonc --output reports/graph.expanded.svg
PYTHONPATH=src python3 -m vibeflow review \
  --workspace vibeflow_config.jsonc \
  --config project/configs/main.jsonc \
  --output reports/graph.expanded.svg
```

`--config`、`--output` 必填；内核 CLI 的 `--workspace` 必填，发布包 `run.py` 只负责注入自己的 workspace。`--output` 不得与 workspace config、workflow config 或登记的架构文档指向同一路径，否则必须在修改任何源文件前 fail closed。该命令不暴露 collapse、theme、layout、hide-contract、Mermaid limit 等自由参数，始终展开 nodeset、保留完整 contract/semantics，并使用默认主题、透明背景和 canonical `review-columns` composer。

维护实现必须保持以下阶段和失败边界：

1. 加载 workspace，解析 workflow 所属 root，并确认它已在该 root 的 `architecture.documents` 中登记。
2. 在不信任旧架构文档的情况下执行 graph/schema/health preflight；失败时不得更新架构文档或调用 renderer。
3. 重新生成登记的 `ARCHITECTURE.jsonc`，再用 canonical check 做字节级复核。
4. 执行正常 workspace validate，使新架构文档也通过正式门禁。
5. 向临时路径调用 canonical expanded SVG renderer。
6. 解析 SVG XML，确认根元素、`aria-roledescription="flowchart-review-columns"` 和至少一个真实 `review-inline-fragment`。
7. 所有检查通过后才替换目标 SVG；失败时删除临时文件并保留原目标文件。

命令不得调用直接 mmdc fallback，也不得把旧 SVG、expanded MMD 或手写图当作审核成功。renderer 阶段失败后，已经成功更新的架构文档可以保留，但 JSON 结果必须返回 `published: false`。标准输出只写一个 JSON 对象，包含 `status`、`failed_stage`、config、architecture、validation、SVG 路径和 `published`；不写 provenance hash、sidecar 路径或额外人类文本。`PASS` / `CONCERNS` 返回 0，`FAIL` / `ERROR` 返回 1，argparse 参数错误返回 2。

`review` 是正式审核入口；现有 `architecture`、`validate`、`svg` 继续作为单项生成和诊断命令。用户要求“审核后再实现”时，即使 `review` 成功也必须等待后续一条明确的用户批准消息，不能把机器检查成功解释成人类确认。

### `review` 回归测试最低集合

- 已登记的有效 workflow 能更新/生成 canonical 架构文档并发布 expanded SVG。
- 缺失、陈旧或非 canonical 架构文档能被重新生成；未登记 workflow 返回 `REVIEW.ARCHITECTURE.UNREGISTERED` 且不生成 SVG。
- graph/schema/health preflight 失败时，架构文档不变且 renderer 未被调用。
- workspace `CONCERNS` 返回 0 并继续生成审核图。
- renderer 异常或 SVG 为空、不可解析、缺 composer 标记、缺真实 fragment 时不发布，原 SVG 保持不变，并分别报告 `svg` 或 `svg_check` 阶段。
- 发布包入口正确注入 workspace；直接内核入口缺少 `--workspace` 时保持 argparse 错误。
- 现有普通 SVG 与 `--expand-nodesets` 行为保持兼容，expanded SVG 仍强制经过 composer。
- 审核产物不生成 `.provenance.json`，也不嵌入 provenance metadata。

## 副作用扫描

通用质量工具默认做结构、依赖图和重复逻辑检查。维护质量工具本身、运行时入口、边界层或其他可能引入 IO 的代码时，可以额外运行：

```bash
PYTHONPATH=src python3 -m vibeflow quality-check --path . --check-side-effects
```

这个选项用于发现文件、网络、数据库、外部进程、环境变量和动态执行等隐藏副作用风险。node/base_lib 的强纯度检查仍由 VibeFlow 自己的 node 健康检查负责，不依赖这个通用选项。

## 维护边界

- `quality-check` 是通用 Python 代码质量工具，不要求目标项目使用 `vibeflow` 架构。
- VibeFlow 仓库自身也通过 `--path .` 使用同一套通用规则自检。
- 不应重新添加只服务本仓库的 `quality-check --self` 分支；仓库专用排除项应通过通用路径扫描规则表达。
- 示例、文档和测试变更也需要经过最终自检，避免维护性 warning 被带入主线。
- 修改审核链路时应优先复用 architecture、workspace validate 和 canonical renderer 的公开内部能力；不要复制一套平行解析、验证或 Mermaid 渲染实现。
