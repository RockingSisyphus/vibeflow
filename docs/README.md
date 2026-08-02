# VibeFlow 文档索引

VibeFlow 0.10.0 使用一个语言无关 Core、一个公共 Block Compiler，以及彼此隔离的 Python 和 JavaScript Target。每个 workspace root 必须用 `project_target` 明确选择一种 Target；单次 workflow 不混用两种语言实现。

## 当前规范

- `developer_guide.md`：共享 workflow/config 语义、Python Runtime 和用户项目质量检查。
- `js_aot_build.md`：JavaScript/TypeScript descriptor、Plugin、Capability、Host Extension、Port 与 AOT 构建。
- `kernel_target_vision.md`：产品目标、分层、公共 IR 和 Target 边界。
- `kernel_development_guide.md`：内核维护、测试、wheel 与分发流程。

正式 Target 名是 `python` 和 `javascript`；TypeScript 是 JavaScript Target 的实现语言。Browser/Node 是单次 JS 构建目标，不是 workflow 声明。端到端用例位于 `../sandbox/python/` 和 `../sandbox/javascript/`。

## 分发文档

- `../distribution/kernel_development_pack/docs/`：进入分发包的主题文档源。
- `../distribution/kernel_development_pack/project_template/README.md`：分发包的人类入口。
- `../distribution/kernel_development_pack/project_template/AGENTS.md`：分发包的 AI 高优先级约束。
- `developer_guide.md` 和 `js_aot_build.md` 会复制到分发包的 `kernel/docs/`。

完整门禁和正式发布：

```bash
python tools/verify_project.py --full
python distribution/build.py
```

正式目录写入 `../dist/vibeflow-distribution/`，确定性归档写入 `../archive/vibeflow-distribution-0.10.0.zip`。临时验证可使用 `--output-dir` 和 `--archive-dir`。

## 两种质量检查

`python -m vibeflow quality-check` 检查用户项目的架构质量。Core Quality 判定语言无关事实，Target 提取本语言事实，Tooling 读取文件并输出报告。它不替代 TypeScript、ESLint 或业务测试。

根目录 `quality/` 是不进入 wheel 的仓库自检器：

```bash
python quality/run.py --profile all
```

它检查目录、依赖方向、Target 隔离、过期文档引用和发布源。工作区清理器默认只预览：

```bash
python tools/clean_workspace.py
python tools/clean_workspace.py --apply
```
