# 架构事实、快照与独立浏览工具

用户入口见[本地预览与历史](../../distribution/docs/user/local-preview.md)。2026-10-19 的重构决定：默认只导出数据，SVG 显式生成；旧版图元快照直接废弃；信息卡片的外框形状与颜色继续响应声明。该决定替代上一版“复用原 SVG 图元”的路线，不改变 Workflow ABI 或调度语义。

## 数据与职责

- Python `PreparedPythonPresentation.architecture()` 缓存同次准备的事实；其 Target-owned 构建入口为 `build_architecture_facts`。JavaScript 的同名公共入口位于 application/javascript/presentation/architecture，由审查和构建共用；规则报告、实现关系和来源归一化在此组装，不通过私有审查函数或拼接审查结果对象导出。
- Python 资源选择在检查边界保存为不可变事实；后续配置被修改或移除，不改变本次导出。原有 compiled_graph.json 序列化收拢到不依赖 Mermaid 的 compiled_document，消费者直接从 compiled_document 导入。
- 准备阶段同时记录是否具有配置来源；纯内存构图保持原有正文边界，已经准备好的真实项目则不因配置后来被移除而丢失资源实现事实。
- 共享 `architecture_facts` 序列化 Architecture 文档；`resource_architecture` 和 `node_presentation` 保留资源来源与有效样式规则。有效连边来自编译结果，网页不推导执行顺序。
- `preview/exporter` 只写 version 2 数据：workflow 身份、Architecture 正文、关联、视图和附件引用。没有重复 body facts、SVG 字符串、图元、96 方向边界或 Mermaid DOM ID。
- `preview/catalog` 负责记录和追加索引，同 ID 通过 revision 合并；重建在扫描前切换索引，避免旧状态覆盖新终态，不设置全局 workflow 锁。
- `presentation/viewer` 只安装独立工具。命令适配器分别发布数据和安装页面；数据写入器不导入网页安装器或 Mermaid。
- 运行观察器公开只读 result，Tooling 在观察器退出后登记终态。保留嵌套 CLI/checked 调用的去重上下文，不再另行根据返回码维护预览终态。非零 CLI 返回码由原观察器记录失败。

## 独立网页与发行

唯一源码位于 tools/workflow-viewer：model 处理加载、调用与类型事实关联及连边角色投影，inspector 展示完整职责、契约、参数和来源，shapes 管理内容测量及原生形状，layout 管理 ELK 层级布局，views 绘制流程/资源/关联，viewer 管理浏览状态和交互。节点形状与连接点复用自身轮廓几何，长契约显示在信息栏。展开调用隐藏原节点卡片，在分组外框顶部显示调用名称和完整说明；标题区域随文字换行预留高度，外部连边连接调用边界。标题及内部均可拖动画布，右键标题或边界可原地收起。

资源视图由 model 按声明类别投影，不扩张到相邻实现资源。Plugin 默认只显示选中的包声明；生命周期贡献不单独成为 Plugin 卡片。BaseLib 保留库间依赖，不混入消费者和所属插件。完整事实继续留在 Architecture，不通过删导出事实实现画布简化。

工具通过配置脚本的 dataRoot 读取经典注册脚本，URL 相对配置位置解析。默认根入口、配置及资源随项目生成；已有配置不覆盖。独立复制工具后修改配置即可浏览数据，不依赖 Python、源码仓库或服务器。原 SVG 是不透明图片附件，只承担平移缩放对照。

显式 SVG 可能晚于数据写入完成。附件引用同时登记到操作元数据，手动刷新通过 revision 获取新附件；不可变架构事实继续使用缓存，原生图的展开和相机状态保持不变。

wheel/sdist 的构建钩子从工具唯一源复制资源；两个发行 profile 的内核 ZIP 直接读取同一源。维护源中不保存第二份浏览器代码。隔离 wheel 构建输入必须包含工具和构建钩子，不能仅复制 Python 包后依赖仓库路径。

## 详情与验收职责

卡片增加简短职责；详情关联调用、NodeType、业务 Node、NodesetType 与资源定义，展示完整说明、有效契约及语义、参数默认值／约束／覆盖和来源。资源卡片复用同一详情入口；Plugin 按完整包展示。全部事实包括关联定义，不再仅序列化调用对象。

连边依据有效 roles、flow_kind 和 join_policy 区分普通流程、可并发分派／等待全部汇合及仅传递数据。数据旁路不参与调度分支计数；决策多出口不直接标为并发。条件与契约摘要绘在边上，完整契约及两端语义进入侧栏。并发标识表达架构中的调度结构，不能代替真实执行时间线。两端事实采集按完整 EdgeSpec 匹配角色，修复相同起终点但条件／调度／传递标志不同的边被合并角色的问题。无需增加快照字段或运行时事件。

HTML 与 Mermaid 按事实、样式意图和交互验收，不要求像素一致。AOT 运行不进行事实导出、页面安装、SVG 渲染及源码编译；构建快照只属于开发阶段。完整验证入口见[开发与验证](development.md)。
