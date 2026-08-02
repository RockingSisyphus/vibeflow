# VibeFlow 文档索引

VibeFlow 0.8.0 将公开 Python API 调整为分层路径。0.8 不保留根级业务导出或旧模块门面；代码示例以当前文档为准。

## 当前文档

- `developer_guide.md`：共享 workflow/config 语义与 Python Target 使用方法。
- `js_aot_build.md`：JavaScript Target 的 JS/TS descriptor、同步/异步 ABI、Capability、Host Extension、Port 和三种 AOT profile。
- `kernel_target_vision.md`：长期产品目标与架构原则。
- `16_语言无关内核与多Target分层架构目标.md`：Core、Block Compiler、两个 Target、Tooling、质量系统与 Sandbox 的当前分层。
- `kernel_development_guide.md`：维护、测试、质量自检、wheel 和分发流程。

正式 Target 名是 `python` 和 `javascript`；TypeScript 是 JavaScript Target 支持的实现语言。端到端用例位于：

- `../sandbox/python/minimal/`
- `../sandbox/python/integration/`
- `../sandbox/javascript/minimal/`
- `../sandbox/javascript/integration/`

## 分发文档

- `../distribution/kernel_development_pack/docs/`：进入分发包的主题文档源。
- `../distribution/kernel_development_pack/project_template/README.md`：分发项目的人类入口。
- `../distribution/kernel_development_pack/project_template/AGENTS.md`：供 AI 开发者使用的高优先级约束。
- `developer_guide.md` 和 `js_aot_build.md` 也会复制到分发内核文档中。

修改源文档后运行完整门禁，再重建分发包：

```bash
python tools/verify_project.py --full
python distribution/build.py --output /tmp/vibeflow-distribution
```

## 质量系统

`python -m vibeflow quality-check` 检查用户项目。Tooling 读取文件，Python 或 JavaScript Target 提取语言事实，Core Quality 统一判定，Tooling 输出 text/JSON 报告。

根目录 `quality/` 是完全独立的 VibeFlow 仓库自检器，不进入 wheel，也不导入 VibeFlow：

```bash
python quality/run.py --profile base
python quality/run.py --profile core
python quality/run.py --profile block-compiler
python quality/run.py --profile python-target
python quality/run.py --profile javascript-target
python quality/run.py --profile all
```

工作区清理器默认只预览：

```bash
python tools/clean_workspace.py
python tools/clean_workspace.py --apply
```

## 设计记录

- `strict_flowchart_kernel_redesign.md`：严格流程图内核设计记录。
- `11_训练性能导向内核改进计划.md`：训练与运行性能改造记录。
- `12_CompiledBlock完整代码生成计划.md`：CompiledBlock 代码生成设计记录。
- `13_CompiledBlock分阶段实施计划.md`：CompiledBlock 分阶段实现记录。
- `14_JS_TS节点与Web_AOT构建计划.md`：JavaScript/TypeScript AOT 设计记录。
- `15_长期工作流与原生IO改造计划.md`：同步/异步入口、永久 loop、Port 与 Host Extension 设计记录。

历史记录解释设计来源，不定义 0.8 公共 API。
