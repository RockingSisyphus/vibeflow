# kernel 目录

这里放分发构建脚本生成的内核资产：

```text
kernel/
  vibeflow-kernel.zip
  MANIFEST.sha256
  README.md
  docs/
  tools/
    mermaid-renderer/
  THIRD_PARTY_NOTICES.md
```

`run.py` 会通过 `sys.path` 直接从 `vibeflow-kernel.zip` 导入本地内核，并用 `MANIFEST.sha256` 校验这些内核资产。业务开发时不需要解包或阅读归档内容。

`docs/` 是给使用者阅读的内核说明，`tools/mermaid-renderer/` 是 SVG 渲染器依赖配置，`THIRD_PARTY_NOTICES.md` 是第三方许可说明。它们可读但不应作为项目内容修改；根目录 `README.md`、`AGENTS.md` 和项目自己的文档才是可定制入口。
