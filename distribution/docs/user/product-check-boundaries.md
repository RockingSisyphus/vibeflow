# 产品检查边界与迁移

VibeFlow 检查明确资源关系、真实调用接口和所选质量政策。PASS 只表示当前检查范围通过，不证明业务结果正确、代码安全、确定性或全部无副作用。项目测试和真实环境验收仍由项目负责。

## Rule 选择

Node 的源码关系由 `vibeflow.node_architecture` 检查；Python 的有限输入写入由 `vibeflow.input_writes` 检查；`vibeflow.no_side_effects` 负责所选效果政策与显式导入政策；`vibeflow.node_interface` 负责实际接口形状。它们通过现有 Rule 图组合，复用同一个 SourceContext。空 Ruleset 不隐式恢复这些源码限制；框架调用、真实 Mapping 和输出键要求仍独立有效。

Python 默认 process/io 等内置集合包含有限输入 Rule：入口 `inputs` 上的索引／属性写入、删除、增量赋值，以及已列出的变更方法，会被报告。同一函数内直线赋值产生的简单别名也受检查，重绑定后不再视为输入别名。复合语句中的直接根引用可检查；复合语句后的不确定绑定不进行路径合并证明。不会追踪跨函数参数、闭包调用、异常出口或生成器消费。未知调用结果、复制结果和复杂取值不是输入别名证明。`mutating_methods` 参数可配置，显式空数组保留其含义。

JavaScript 默认集合不选择 Python 专用输入 Rule；显式选择它会得到 unavailable，不会伪报已检查。两个 Target 统一职责，不强行统一语法覆盖。

## 正常业务代码

局部 while、私有算法递归、普通对象字段、内存对象 close/write、动态输出 Mapping 构造、同名输入类型／输出键、Decision 自定义端口名和示例 outputs，不再仅因旧行为猜测被拒绝。明确另一 Node 调用和内部访问、真实图循环、Nodeset/Loop 结构、所选复杂度限制、明确文件／网络／宿主操作仍按实际机制处理。

JS eval、Function 等动态求值不因无法证明安全而默认拒绝；实际非静态导入协议和无人收尾的定时任务仍按对应机制检查。JS Date、performance、Math 动态成员与随机数不承担默认确定性证明。实际 fetch、文件、DOM、进程生命周期和 crypto 的其他宿主关系仍受对应效果政策约束。

## 工具链与格式

工具链检查实际解析到的 Node、TypeScript 和 esbuild，以及已有兼容版本要求。没有 lock、使用 yarn.lock 或 pnpm-lock.yaml，不会仅因缺少指定 npm lock 被拒绝。项目依然负责安装依赖；框架不会代替包管理器证明安装可重复性。构建工具信息仅保留真实版本字段。

当前源码使用 Workflow ABI `vibeflow.workflow.v8` 与 AOT manifest `vibeflow.aot-build.v3`。runtime_dispatch 推断字段及展示已退役；实际执行锁、调度、异步所有权和资源 cleanup 保留。升级旧版本时，计划、Architecture 与构建产物需重新生成，不提供旧字段兼容读取层。

公开 checked 读取实际完成的 Rule 结果；unavailable 或未选择不会宣称已检查。完整 Rule 结果和未检查的业务／安全范围仍可查看。
