# 本地预览与历史

发行包根目录的 `vibeflow-preview.html` 可直接离线打开。页面资源位于 `vibeflow-preview/assets/`，数据位置由 `vibeflow-preview.config.js` 配置；初始历史为空。

## 生成与交付审核材料

```bash
python run.py review --config <root>/configs/main.jsonc
```

`review` 对真实 Config 生成 HTML 审核快照，并返回 `preview`（HTML 完整路径）和 `preview_id`。交付审核材料时提供这两个字段及 `vibeflow-preview.html#snapshot=<preview_id>&view=flow` 定位链接，说明对应 Config 与变更位置，请用户查看当次 workflow。

HTML 使用结构化快照与离线 ELK 排版。

## 浏览流程与资源

| 操作 | 行为 |
| --- | --- |
| 单击节点 | 查看调用职责、类型、完整契约与语义、参数、约束及来源 |
| 单击连线 | 查看条件、调度／数据传递标志、角色与两端契约 |
| 右键 Nodeset 或 Loop | 在具体调用处展开或收起；默认折叠 |
| 拖动画布、节点或容器标题 | 平移画布 |
| 滚轮或比例输入 | 缩放；输入接受任意有限正数 |
| 定位隐藏节点 | 自动展开其祖先调用 |

展开后，调用名称和说明显示在容器顶部，外部连线接到调用边界；收起后恢复节点卡片。互不连通的入口分支保持快照中的排列顺序，不因展开后的尺寸变化而交换位置。手动展开状态只影响当前视图。

planned Node、Nodeset 和 Loop 使用虚线外框与 60% 不透明度，保留业务／操作颜色；嵌套透明度按一次应用。侧栏分别显示调用与定义的状态及有效计划行为。有内部定义的 planned Nodeset 可展开，缺少定义时显示“暂无内部定义”。规划状态、实现状态和运行结果分别呈现。

节点支持 14 种形状，并保留颜色、图标和调用级覆盖。普通 process 的多路分发及多前驱 `all` 汇合默认使用双圆形；显式样式优先。黑色实线表示正常流程，蓝绿色实线表示可能并发的分派或汇合，灰色虚线表示只传数据。并发标识来自有效调度边与汇合策略，实际并发还受条件、锁和额度影响。

Plugin 视图每个所选包显示一张卡片；BaseLib 视图显示独立库及库间依赖。包内类型、规则和私有库的完整事实保存在快照详情，空视图给出说明。

## 命名入口与跨 workflow 跳转

页面可查看全部入口或指定入口。运行记录首次打开时选择实际运行入口，查看其他入口只改变浏览范围。

InvokeSync、Call、Wait、Send、Receive、Kill 使用缺角卡片（`notch-rect`），InvokeSync 为浅绿色，Call 为金色，Wait 为灰色，Send 为浅蓝色，Receive 为深蓝色，Kill 为红色。附带 wait 保留主操作配色，多个主操作使用组合样式。显式外观与 planned 状态继续优先。

InvokeSync/Call/Kill 从 `config.workflow` 生成目标关联；Send/Receive 从 `config.expected_workflows` 生成预期关联。右键菜单跳转到目标 workflow，Call 的目标入口随之选中。root 的 `preview.workflow_links` 可添加说明性关联。操作配置见[Workflow 协同](workflow-coordination.md)。

跳转后恢复目标上次选择的记录；首次进入选择目标最新快照。目标没有独立记录时使用本次快照携带的目标事实，标注“本次关联快照”；只有历史关联时，选取来源时刻之前最近的目标快照。缺少目标、入口或资源时显示具体原因。workflow 跳转使用独立视图，Nodeset 在原调用处展开。

地址 fragment 保存快照、workflow、视图和调用路径，支持浏览器后退。调用路径以 `/` 分层，单个 ID 中的 `/`、`%` 等字符使用 URL 百分号编码，例如 ID `a/b` 写成 `a%2Fb`。

## 历史与项目目录

`review`、`build`、Python 源码 `run` / `delegate-cli` 登记审查、构建、运行快照。历史显示操作和实际状态；中断后保留“审查中”或“运行中／未记录结束”。预览生成失败时，review 报错，build 与业务运行记录原因后继续。JS 与两端 AOT 的产物执行仅记录各自运行资料。

`validate`、`quality-check` 和显式导出只执行各自操作。运行日志、trace、状态和业务输出保存在 run 目录，`preview.json` 指向集中预览快照。

“项目目录 · 最新快照”按注册 root 列出识别及登记的 workflow，每项显示最新快照、结果和时间；缺少快照时显示源文件时间，损坏登记项显示诊断，空 root 保持可见。最新记录按生成时间选择，旧运行稍后结束仍保留原有顺序。历史模式保留全部记录及筛选。

顶部“项目结构与 workflow 总览”默认收起，展开后可浏览目录、root 与 workflow；架构资料的阅读及更新方法见[架构指南](architecture.md)。页面“刷新列表／历史”重读已导出数据，保留当前选择与画布。项目模式缺少目录时提示更新，已有快照仍可从历史模式查看。

## 移动、配置与索引恢复

预览统一写入所属项目根目录，`--preview-root DIR` 可重定向。整体移动 HTML、配置 JS 和同级数据目录后可继续离线查看，路径支持中文与空格。历史默认保留。恢复索引使用：

```bash
python run.py preview --reindex --preview-root DIR
```

此命令从现有快照的 `record.json` 重建索引。数据格式升级见[迁移说明](rule-system-migration.md)。

配置示例：

```js
window.VibeFlowViewerConfig = {
  dataRoot: new URL("./vibeflow-preview/", document.currentScript.src).href
};
```

相对路径以配置文件所在目录为基准，重新生成预览保留已有配置。查看器可单独部署，配置数据目录即可浏览快照。

索引通过 `VibeFlowPreview.record(metadata)` 登记列表元数据，同一操作按较大 revision 更新；选中记录后加载 `snapshots/<ID>/snapshot.js` 的 `VibeFlowPreview.snapshot(data)`。本地经典脚本支持离线读取，快照保存流程、资源、视图、关联。


`review` 的 JSON 审查结果写到标准输出。如需保存报告，可使用 shell 重定向：

```bash
python run.py review --config <root>/configs/main.jsonc > review-report.json
```

使用 `--preview-root` 指定离线预览目录。
