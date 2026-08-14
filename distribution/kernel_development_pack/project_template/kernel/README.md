# VibeFlow kernel 资产

本目录包含发行包使用的内核归档、完整性清单、使用者文档、许可证和 SVG 渲染器配置。`run.py` 从 `vibeflow-kernel.zip` 导入固定版本内核，并用 `MANIFEST.sha256` 校验受保护资产。

开发业务项目时从 `kernel/docs/README.md` 进入使用者手册，修改 `python_project/` 或 `javascript_project/` 中的真实 source。kernel 资产由 VibeFlow 发行构建生成。
