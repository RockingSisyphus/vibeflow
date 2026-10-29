# 产品检查范围

VibeFlow 检查显式资源关系、真实调用接口和所选质量政策。PASS 表示本次实际检查通过；业务正确性由项目测试确认，外部行为由真实环境验收确认。源码检查提供有限静态分析，运行环境的安全隔离由宿主负责。

## 源码检查

| Rule | 职责 |
| --- | --- |
| `vibeflow.node_architecture` | 源码资源关系 |
| `vibeflow.input_writes` | Python 的有限输入写入检查 |
| `vibeflow.no_side_effects` | 所选效果政策与显式 import policy |
| `vibeflow.node_interface` | 实际调用接口形状 |

这些检查复用 SourceContext，按资源所选 import/static/run 入口执行。`checked` 取实际完成的 Rule 结果，未选择或 unavailable 的检查分别记录。空 Ruleset 取消相应源码规则；运行时仍按调用协议检查 Mapping 与输出键。

## 输入写入分析

Python 默认 process/io 等集合包含有限输入 Rule，识别入口 `inputs` 上的索引／属性写入、删除、增量赋值及配置的变更方法。同函数直线赋值形成的简单别名也受检查，重绑定后结束别名关系；复合语句内的直接根引用仍可检查。

覆盖以这些静态关系为限：复合语句后的路径合并、跨函数参数、闭包调用、异常出口、生成器消费、未知调用与复杂取值需由项目测试覆盖。`mutating_methods` 可配置，空数组表示空方法选择。

JavaScript 默认集合使用对应 Target 的源码规则；显式选择 Python 专用输入 Rule 时报告 unavailable。

## 普通业务代码与效果政策

局部 while、私有算法递归、普通对象字段、内存对象 close/write、动态输出 Mapping、同名输入类型／输出键和自定义 Decision 端口可按原生语言编写。显式 Node 调用、资源内部访问、图循环、子图结构、复杂度限制和文件／网络／宿主操作按对应规则处理。

JS 的 eval、Function、Date、performance、Math 动态成员与随机数使用原生语言语义。非静态导入、无人收尾的定时任务、fetch、文件、DOM、进程生命周期和 crypto 宿主操作仍按对应效果政策检查。默认源码规则覆盖已识别模式，确定性及完整副作用行为由项目按自身需求验证。

## 工具链

工具链检查实际解析到的 Node、TypeScript、esbuild 版本及兼容要求。项目可以使用 npm、Yarn 或 pnpm 安装依赖；锁文件及安装可重复性由项目的包管理流程维护。构建资料记录真实工具版本。
