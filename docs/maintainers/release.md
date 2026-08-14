# 发行与文档装配

VibeFlow 0.13.2 默认发布 collaborative 与 autonomous 两个开发包。两者共享 Core、机器 policy、最小 Python/JavaScript 项目和 Workflow ABI。

## Profile 配置

`distribution/profiles.jsonc` 是 profile 的唯一配置源，schema 为 `vibeflow.distribution-profiles.v1`。路径使用仓库相对形式：prompt 来自 `distribution/prompts/`，发行正文来自 `docs/overview.md` 与 `docs/user/`。

公共文档集进入两个包；每个包只选择自己的 profile 协议。`docs/design/` 与 `docs/maintainers/` 不允许进入发行文档集。

## 构建

```bash
python distribution/build.py
```

默认以一个事务发布两个目录和两个确定性 ZIP。构建先在临时目录生成、验证和归档全部 profile；任一阶段失败时不替换旧发行物。

单 profile 构建保留给测试和局部验证：

```bash
python distribution/build.py --profile collaborative --output-dir /tmp/vf-collaborative
python distribution/build.py --profile autonomous --output-dir /tmp/vf-autonomous
```

## 文档装配

构建器按 profile 复制 canonical 用户文档并保留其相对路径，生成 `kernel/docs/README.md` 导航，再从 prompt fragments 确定性合成根 `AGENTS.md`。根 README 只提供 profile、最小项目和文档入口。

完整性检查验证文档集合、字节内容、AGENTS、metadata、manifest 和 kernel hash。两个 profile 的 kernel ZIP、项目模板和机器 policy 必须字节一致。
