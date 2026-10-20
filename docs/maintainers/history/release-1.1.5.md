# VibeFlow 1.1.5

本地分发包构建说明，2026-10-20；尚未提交、推送或发布 GitHub Release。

## 中文更新

- Python AOT 在 Bundle 加载时一次准备固定节点／运行插件描述及节点路径；固定插件绑定表在首次使用时建立并由该 Bundle 复用。
- 每次 Runtime 继续拥有独立注册表、Node、参数和插件生命周期实例；跨项目模块隔离、异常清理与取消语义保持原有实现。没有全局缓存或第二套执行器，SDK bindings() 返回行为不变。
- Workflow ABI v8、AOT manifest v3 和快照 v2 不变。已有 AOT 包须重新构建以更新内嵌框架，不需要迁移业务配置。AOT 执行不新增预览报告。
- 两个 profile 均包含修复，并保留解压即可打开的离线 HTML 入口。JS 空钩子问题仅保留沙盒诊断，本版未修改 JS 内核。

## 验证范围

修复阶段 108 项相关回归通过，覆盖并发、跨 Bundle、配置、Node／插件实例隔离、生命周期、取消、trace、Loop／Nodeset、包内框架与源码移除部署。原 139 节点实包五次暖调用的固定 Descriptor 解析和完整绑定表构造均降为零。项目质检通过。

本次打包另验证两个正式 ZIP 的内嵌加载器、包内 Python AOT 构建与独立 Runtime 执行，结果见仓库旁 `VibeFlow-evidence/build-1.1.5-20261020`。未重复完整测试门禁，也未运行原 Windows 120 秒整组。

## English

Prepare fixed Python AOT descriptors and paths once per bundle, and reuse its lazily loaded plugin binding index. Keep registries, Node instances, parameters and runtime plugin lifecycles independent. SDK bindings(), Workflow ABI v8, AOT manifest v3 and snapshot v2 remain unchanged.

Rebuild existing AOT artifacts to include the updated embedded framework. Both local distribution profiles retain their offline HTML entry. The 108 related regressions passed; Windows full-group timeouts have not been revalidated. This local build has not been published to GitHub.
