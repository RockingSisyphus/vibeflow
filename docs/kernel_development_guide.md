# Kernel 开发者工作流

本文档面向维护 `topology-kernel` 自身的开发者，不是面向业务项目编写 node、nodeset 或 plugin 的使用者指南。

## 基本验证流程

修改 kernel 代码后，默认运行以下命令：

```bash
PYTHONPATH=src python3 -m pytest tests/unit -q
python3 -m compileall -q src tests examples
PYTHONPATH=src python3 examples/integration_sandbox/run_all.py
PYTHONPATH=src python3 -m topology_kernel quality-check --path .
```

其中最后一条是通用代码质量自检。它不再有仓库专属的 `--self` 模式；检查 kernel 仓库自身时统一传入当前仓库路径 `.`。

验收标准：

- `quality-check` 必须输出 `PASS`。
- `errors` 必须为 `0`。
- `warnings` 必须为 `0`。
- 若新增代码触发 warning，优先重构新增代码；不要为了通过检查而随意放宽通用质量规则。

## 副作用扫描

通用质量工具默认做结构、依赖图和重复逻辑检查。维护质量工具本身、运行时入口、边界层或其他可能引入 IO 的代码时，可以额外运行：

```bash
PYTHONPATH=src python3 -m topology_kernel quality-check --path . --check-side-effects
```

这个选项用于发现文件、网络、数据库、外部进程、环境变量和动态执行等隐藏副作用风险。node/base_lib 的强纯度检查仍由 kernel 自己的 node 健康检查负责，不依赖这个通用选项。

## 维护边界

- `quality-check` 是通用 Python 代码质量工具，不要求目标项目使用 `topology-kernel` 架构。
- kernel 仓库自身也通过 `--path .` 使用同一套通用规则自检。
- 不应重新添加只服务本仓库的 `quality-check --self` 分支；仓库专用排除项应通过通用路径扫描规则表达。
- 示例、文档和测试变更也需要经过最终自检，避免维护性 warning 被带入主线。
