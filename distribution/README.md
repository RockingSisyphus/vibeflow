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
