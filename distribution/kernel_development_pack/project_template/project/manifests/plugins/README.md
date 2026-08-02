# Plugin descriptors

JavaScript/TypeScript Plugin 每个资源使用一个 `.jsonc` descriptor，并由 workflow 顶层 `plugins` 按稳定 ID 选择。Python Plugin 继续通过 `project/registry.py` 注册，不放在此目录。

接口、planned 语义和 Plugin/Host Extension 边界见 `kernel/docs/06_Plugin开发规范.md`。
