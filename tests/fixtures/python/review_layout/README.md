# Python 正式 SVG 布局回归

这组沙箱使用公开 SDK 声明 Node、BaseLib、compiler/runtime Plugin，通过四个正式 CLI 入口检查布局。它同时包含两层 Nodeset、同一定义的重复调用、Loop，以及 Node 的默认圆角形状和调用点颜色覆盖。所有场景使用新进程和独立项目目录。

```bash
python -B tests/fixtures/python/review_layout/run_all.py \
  --kernel src \
  --work /tmp/vf-review-layout-current \
  --report /tmp/vf-review-layout-current.json \
  --renderer /path/to/installed/mermaid-renderer
```

`--kernel` 支持源码目录或含 `src/` 的仓库目录；`--renderer` 使用已有锁定工具链。运行器不会安装依赖。缺少场景、CLI 失败、渲染失败、浏览器观察失败均使整组退出码为 1，不跳过验收。

四个稳定案例在 [cases.json](cases.json) 中登记：

- `layout.review.nested_repeat_loop`：正式 review 更新 Architecture，并生成真实展开 SVG。
- `layout.expanded_svg.nested_repeat_loop`：正式 `export-svg --expand-nodesets`。
- `layout.mermaid.explicit_resources`：普通 Mermaid 导出继续显示调用方明确选择的资源。
- `layout.ordinary_svg.explicit_resources`：普通折叠 SVG 保留明确选择的资源，并检查实际浏览器几何。

展开产物按主 Workflow、`plugins`、`base_lib`、逐个展开的 Nodeset/Loop 面板排列；这份夹具没有 Host，`host_extensions` 列省略。`plugins` 父节点连接当前 config 选中的插件包，`base_lib` 父节点连接实际选择的库。外层流程为 TD；有子 Nodeset 的父流程为 TD；叶子流程为 LR。父流程在左，子面板在右且纵向堆叠。同一定义的重复调用保留调用 ID，合并为同一个详情面板；Loop 保留独立调用分组。

观察器只包装实际渲染函数，保存它们收到的 Mermaid 和标题，继续调用原渲染器。当前每次展开必须观察到 9 个真实 Mermaid 分片、4 列和 2 个嵌套面板；资源目录采用 LR 方向。业务分片不得包含资源图节点；资源目录不得出现文件图、reference、Node type 或 Rule/Ruleset 拓扑，同一插件包不拆成 compiler/runtime 实现卡。最终 SVG 在真实 Puppeteer 浏览器中检查业务方向、资源区域隔离、圆角形状、Node 默认色、调用点覆盖色和资源声明的六边形及颜色。正式 Architecture 同时检查样式值与逐字段来源。截图和逐分片 Mermaid 随报告保存至 `evidence/<report-stem>/`。

浏览器的节点 ID 含渲染器前后缀，且 Mermaid 保留字 `end` 会被 VibeFlow 转为 `n_end`。定位器按实际分片归属及逻辑节点 ID 识别，方向和颜色期待保持不变。

`review-layout-sandbox` 由 [完整验证入口](../../../../docs/maintainers/development.md#验证层级)执行。Nodeset 折叠、默认值及内部图隔离的专项命令与断言见[用户资源目录专项](../resource_sections/README.md)。验收结果以实际运行生成的报告为准。

## 目录用途与边界

仅用于：review_layout 专项实现回归的固定输入、预期及 runner；只保留有当前加载方的材料，运行产物写入临时工作区。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../../docs/maintainers/directory-layout.md)。
