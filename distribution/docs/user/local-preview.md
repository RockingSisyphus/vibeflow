# 本地预览与历史

`review`、`build` 和 Python 源码 `run` / `delegate-cli` 会在工作区根目录
生成 `vibeflow-preview.html`，并把展示数据保存在同级 `vibeflow-preview/`。
独立项目使用项目根目录；`--preview-root DIR` 可以重定向两者。双击 HTML
即可离线查看，不需要启动服务或安装前端依赖。默认只导出事实，不启动 Mermaid 或浏览器。可选 SVG 对照仍使用发行包的 Mermaid 渲染依赖。

```bash
python run.py review --config project/configs/main.jsonc
python run.py review --config project/configs/main.jsonc --with-svg
python run.py review --config project/configs/main.jsonc --output review.svg
python run.py preview --reindex
```

`review` 的 JSON 结果包含 `preview`（HTML 完整路径）和 `preview_id`。交付审核时提供入口及当次快照定位链接，例如 `vibeflow-preview.html#snapshot=<preview_id>&view=flow`，说明对应 Config 和变更位置，请用户查看该快照；仅报告生成成功或提供 SVG 不等于交付 HTML 审核材料。

源码检出可以使用 `python -m vibeflow`。`review --output` 是可选的；显式指定时
仍生成原来的审查 SVG，并同时登记历史。`validate`、`quality-check` 和显式导出
不会登记历史。运行日志、trace、状态文件和业务输出仍在原来的 run 目录；
`preview.json` 指向该次运行的展示快照。自动图形不再重复写入 run 目录。
原有 Architecture 登记文档仍按原位置更新。

历史区分别显示审查、构建、运行及真实状态。审查图形仍在生成时会显示“审查中”，
完成后才标为审查通过；中途退出不会被推断为通过。运行中的记录如果未收到结束更新，
会保持“运行中 / 未记录结束”，不会推断为成功。预览失败不会阻止构建或业务执行，
会显示具体错误；以生成预览为目的的 review 则报告失败。第一版不记录 JavaScript
或两端 AOT 的运行历史。

AOT 产物执行不采集架构事实、不生成预览、不触发图检查或渲染器。构建命令的快照在开发阶段生成一次，不进入产物运行路径；原有业务运行日志与状态输出遵循运行选项。

“结构化”直接读取 Architecture 事实，由网页测量信息卡片、自主绘制形状并使用离线 ELK 排版，
不读取 Mermaid 图元。14 种合法形状保留近似轮廓，颜色、图标和调用级覆盖保持声明意图。
“原 SVG 对照”显示显式请求的独立附件，只提供平移缩放；缺少附件时提示使用 `review --with-svg`。
Nodeset 与 Loop 默认折叠，右键选择原地展开或收起，不改变配置的 `expand`。
展开容器的外部连线连接调用边界。左键拖拽任何节点或容器内部均平移画布，
滚轮缩放；比例输入接受任意有限正数，不设固定上限。定位隐藏节点会展开其祖先。

planned Node 和目标定义为 planned 的 Nodeset / Loop 均显示计划状态；侧栏分别保留调用声明与目标定义状态，计划行为采用本次事实中已解析的有效值。Nodeset 有内部定义时可右键展开；没有内部定义时明确标注“暂无内部定义”并禁用展开。规划、已实现与实际运行结果分别报告，不从图形推断运行成功。

卡片显示简短职责说明；单击节点可查看调用职责、类型说明、完整输入输出契约与语义、默认参数、调用参数、参数约束及来源。未提供的信息不会凭空补写，展开“全部事实”可核对对应调用、类型和 Nodeset 定义。

黑色实线表示正常流程，蓝绿色实线表示可能并发分派或等待全部分支汇合，灰色虚线表示仅传递数据、不触发调度。条件和数据契约摘要标在边上，单击连线可查看完整条件、角色、调度／数据传递标志和两端契约。并发标识依据有效调度边与汇合策略；实际是否同时执行仍受条件、锁与并发限制影响。数据虚线不参与调度分支计数，条件决策的多出口不会被当成并发分派。

流程、BaseLib、Plugin、Host Extension 和 workflow 关联通过视图描述列表登记。
资源图只显示准备结果中已有的资源、声明、来源及依赖事实；空视图会明确说明。
页面不会回退到示例数据。手动“刷新历史”保留当前选择和画布，不后台轮询。

在 `vibeflow_project.jsonc` 中声明关联：

```json
{
  "project_target": "python",
  "preview": {
    "workflow_links": [{
      "from_workflow": "configs/main.jsonc",
      "from_call_path": "prepare/child",
      "to_root": "worker",
      "to_workflow": "configs/task.jsonc",
      "kind": "call",
      "label": "任务工作流"
    }]
  }
}
```

路径相对各自 root，`from_call_path` 和 `label` 可省略，`kind` 为 `call` 或
`reference`。关联仅用于展示，不改变调度，也不采集真实运行父子关系。所有 root
的快照统一写入所属工作区预览目录时，可跨 root 跳转。目标选择当前记录时间之前
最近的一份快照；没有时显示配置路径和缺失说明，不跳到未来快照。
浏览器地址的 fragment 记录快照、workflow、视图与调用路径，可用后退返回。
调用路径以 `/` 分隔节点 ID；单个 ID 中的 `/`、`%` 等字符使用 URL 百分号编码，
例如 ID `a/b` 对应 `a%2Fb`，不会与两层调用 `a/b` 混淆。

整体移动 HTML、`vibeflow-preview.config.js` 和同级数据目录后仍可打开，包括中文和带空格的路径。不要单独
移动 HTML。历史默认保留，不迁移旧 runs，不自动清理。
索引损坏时可运行 `preview --reindex --preview-root DIR`；此命令只读取已有快照
的 `record.json` 重建索引，不重新检查源码或重新渲染。

实现数据格式为版本 2，不读取或迁移旧版图元快照。
查看器源码独立位于 `tools/workflow-viewer`；安装后的配置文件示例：

```js
window.VibeFlowViewerConfig = {
  dataRoot: new URL("./vibeflow-preview/", document.currentScript.src).href
};
```

相对路径按配置文件所在目录解析；重新生成预览不会覆盖已有配置。也可以单独复制工具目录，
调整其 `preview.config.js` 后浏览其他目录的数据，无须 VibeFlow 运行环境。

`index.js` 中每行是 `VibeFlowPreview.record(metadata)`；
同一操作 ID 以较大的 revision 更新状态，索引重建中的旧记录不会倒退已完成状态。`snapshots/<ID>/snapshot.js` 通过
`VibeFlowPreview.snapshot(data)` 注册展示数据。索引只包含列表元数据，选中时
才加载快照；页面使用本地经典脚本，不通过 `fetch` 读取 JSON。
快照正文只含 Architecture、视图、关联和可选附件引用，不内嵌 SVG 或重复节点图元。
