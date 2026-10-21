# Python 用户资源目录与 Nodeset 折叠

通过公开 SDK 声明 Node、BaseLib、compiler/runtime Plugin 和领域 Rule，用正式命令验收当前 config 的资源目录、定义层 `expand`、同定义重复调用与 Loop。共 14 个固定案例，复用[布局沙箱](../review_layout/README.md)的真实嵌套流程及浏览器观察器。

```bash
python -B tests/fixtures/python/resource_sections/run_all.py \
  --kernel src --work /tmp/vf-python-resource-sections \
  --report /tmp/vf-python-resource-sections.json \
  --renderer /tmp/vf-adaptation-full-accepted/puppeteer
```

运行器不安装依赖。每个案例使用独立项目和新 CLI 进程；检查与执行案例先通过正式 `export-architecture` 生成登记文档。缺失产物、非预期退出码、错误 Rule 来源、观察异常或浏览器失败都会导致非零退出。

固定案例覆盖正式 SVG、Mermaid 的目录父节点及所选资源子节点、外层折叠、共享叶子折叠与可见兄弟、独立 Loop body、ASCII、validate、quality-check、隐藏实现的目标健康错误和真实 checked run。三个历史 `*.rules` 案例 ID 保留，期待改为删除的 `--show-rules` 被 argparse 明确拒绝、退出码 2 且不发布产物；不再通过该参数把内部规则图混入用户 SVG。Rule 参数 schema/defaults 显式声明；非法健康案例只接受 `CASE.HIDDEN.SOURCE`、error 严重度和实际源码行。折叠后真实运行仍执行内部 Node；原生数值与执行格式对照另外覆盖三种 Python 执行模式。

默认及外层折叠 SVG 在真实浏览器中检查节点几何、资源声明颜色及形状，保存 DOM 与截图。全部图形禁止文件拓扑、reference、Node type 和 Rule/Ruleset 框。颜色、形状、横竖方向及相邻区块的几何回归还由原四个布局案例验收。Host 的真实实例见[JS 资源专项](../../javascript/resource_sections/README.md)。

新组与原布局组均进入 `verify_project.py --full`，不会将未执行案例视为通过。`expand` 仅控制图形，完整架构 JSON、所选审查和运行仍使用内部定义。

## 目录用途与边界

仅用于：resource_sections 专项实现回归的固定输入、预期及 runner；只保留有当前加载方的材料，运行产物写入临时工作区。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../../docs/maintainers/directory-layout.md)。
