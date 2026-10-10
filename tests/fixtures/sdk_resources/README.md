# 固定 SDK 回归项目

这些项目直接导出固定 Python/JavaScript SDK Plugin 与完整资源声明。测试复制对应项目后，可以编辑所需 SDK 资源和实现源码；不存在 Registry、manifest、bundle 发现或运行时迁移。

目录沿用 sandbox 路径，便于 `copy_sdk_inputs` 将固定测试源码覆盖到临时项目。正式可运行示例仍位于 sandbox；不再加载的旧资源输入已经删除，历史原文可在 Git 提交 `665e06e` 中查阅。
