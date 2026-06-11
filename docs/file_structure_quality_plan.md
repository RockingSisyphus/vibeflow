# 文件结构质量检查计划

## 当前目标

`quality-check` 是一个通用 Python 代码质量检查工具，不再包含针对本仓库主体 `a` 的专属模式。

当前唯一入口形态是：

```bash
topology-kernel quality-check --path <project-or-file>
```

## 设计原则

- 不内置特定项目名称、目录名或层级假设。
- 默认规则应适用于普通 Python 项目。
- 高噪声规则必须显式启用，例如副作用 API 检查。
- 结构规则只使用可解释信号：路径、文件名、import 图、前缀簇、扇入扇出、依赖距离。
- finding 的 `details` 必须给出可复核依据。

## 默认启用能力

- 文件大小、函数大小、分支数、嵌套深度。
- Python 语法错误。
- import cycle、双向依赖、依赖链深度。
- duplicate AST fingerprint。
- 目录图和结构摘要。
- 同前缀功能簇识别。
- 内部模块命名启发式。
- 公共入口绕过启发式。
- 依赖距离与分散依赖启发式。
- 结构迁移建议。

## 显式启用能力

副作用 API 检查默认关闭，需要显式启用：

```bash
topology-kernel quality-check --path <project-or-file> --check-side-effects
```

原因：

- 普通 Python 项目中的 CLI、测试、构建脚本经常合法读写文件。
- 默认启用会产生大量噪声。
- node/base_lib 纯度检查仍有自己的强副作用约束，不依赖通用代码质量工具默认开启。

## 不再保留的能力

- 本仓库专属自检模式。
- 本仓库专属架构 contract。
- 本仓库专属 side-effect allowlist。
- production/tests/core/devtools/CLI 等硬编码分层规则。

这些能力如果未来需要恢复，必须通过通用配置文件或用户显式声明实现，而不是写死在工具里。
