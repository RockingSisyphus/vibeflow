<!-- vibeflow-directory-purpose -->
# .github/workflows

## 目录用途与边界

仅用于：GitHub Actions 工作流配置；本地验证入口维护在 tools，产品构建逻辑维护在 distribution。

`ci.yml` 在 Node 22 / 24 与 Python 3.11 上运行当前 `tools/verify_project.py --full`，覆盖仓库质检、隔离 pytest、规则与真实沙箱、浏览器、wheel 和双 profile 发行。使用 runner 临时目录及 4 个测试 worker；无论成功失败，上传日志与分阶段结果供定位。`release.yml` 仅手动触发：检出已验证标签，核对完整提交，从 Git blob 取得已验证的两个原始 ZIP，核对预期 SHA256 后上传到已有空草稿、下载校验并发布。写权限限于发布 job，使用 GitHub 提供的 job token，不接受自定义凭据；不覆盖已有资产或移动标签。具体发布步骤见[发行维护](../../docs/maintainers/release.md)。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../docs/maintainers/directory-layout.md)。
