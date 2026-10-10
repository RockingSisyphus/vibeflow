# 发行资源

这里维护构建器、`profiles.jsonc`、提示词、内核开发包模板、最小项目及[用户文档原稿](docs/README.md)。开发设计和审核记录在 [docs](../docs/README.md)。

```bash
python distribution/build.py
```

最新的 collaborative / autonomous 目录及 ZIP 进入 `dist`；被替换的正式 ZIP 进入 `archive`。`--archive-dir` 指定本次 ZIP 的输出目录，默认跟随输出目录放在其旁边，正式构建时是 `dist`；名称中的 archive 指 ZIP 格式。

候选包验证应同时显式指定仓库外的输出目录和 ZIP 目录，避免覆盖正式产物：

```bash
python distribution/build.py --profile collaborative \
  --output-dir /tmp/vf-candidate/collaborative \
  --archive-dir /tmp/vf-candidate/packages
```

完整验证入口自动在临时目录构建并检查两个 profile，结束后清理。

## 目录用途与边界

仅用于：发行构建器、profile 配置、提示词、用户手册原稿与项目模板；正式生成结果归 dist。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../docs/maintainers/directory-layout.md)。
