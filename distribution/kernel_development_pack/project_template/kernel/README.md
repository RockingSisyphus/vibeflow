# VibeFlow kernel 资产


开发业务项目时从 `kernel/docs/README.md` 进入使用者手册，修改 `vibeflow_config.jsonc` 登记的业务 root 中的真实源码。root 目录名和 ID 可以自定义，修改方法见分发包根目录下的 `kernel/docs/user/project-governance.md`。kernel 资产由 VibeFlow 发行构建生成。

本目录包含内核归档、完整性清单、使用者文档及许可证。`run.py` 从固定版本内核归档导入，并校验受保护资产。

根目录的 `DISTRIBUTION.json` 只描述原始发行包身份，不配置业务项目；改 root 无需修改它或重写完整性清单。
