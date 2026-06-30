from __future__ import annotations

from topology_kernel import NodeContract, NodeInfo


class PrepareValueNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.prepare_value",
        display_name="初始化并准备业务数值",
        category="sandbox",
        description="把原始输入数值转换为后续核心计算可以直接使用的准备态数据；该节点模拟真实程序中读取配置、补默认值、做轻量初始化的准备阶段。",
        version="0.1.0",
        flow_kind="preparation",
    )
    CONTRACT = NodeContract(
        requires=("value.in",),
        provides=("value.prepared",),
        input_semantics={"value.in": ("调用方传入的原始业务数值，尚未经过初始化偏移处理。",)},
        output_semantics={"value.prepared": ("value.prepared：已经加上初始化偏移量、可以交给核心计算子流程使用的准备态数值。",)},
        params_schema={"offset": {"type": "number", "description": "初始化阶段叠加到原始输入上的偏移量，用来模拟默认配置或预处理修正。"}},
        output_schema={"value.prepared": {"type": "number"}},
        examples=({"inputs": {"value.in": 3}, "params": {"offset": 1}, "outputs": {"value.prepared": 4}},),
    )

    def run_pure(self, inputs, params):
        return {"value.prepared": inputs["value.in"] + params.get("offset", 0)}


class CoreComputeNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.core_compute",
        display_name="核心业务计算",
        category="sandbox",
        description="在预定义子流程中执行主要计算逻辑；综合示例把它放进 nodeset，验证预定义过程节点与内部流程图的一致性。",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("value.prepared",),
        provides=("value.out",),
        input_semantics={"value.prepared": ("准备阶段输出的数值，已经满足核心计算的输入前置条件。",)},
        output_semantics={"value.out": ("核心计算得到的中间业务结果，后续会进入决策节点判断是否继续循环。",)},
        params_schema={"factor": {"type": "number", "description": "核心计算使用的乘数，用于放大准备态数值。"}},
        output_schema={"value.out": {"type": "number"}},
        examples=({"inputs": {"value.prepared": 4}, "params": {"factor": 2}, "outputs": {"value.out": 8}},),
    )

    def run_pure(self, inputs, params):
        return {"value.out": inputs["value.prepared"] * params.get("factor", 2)}


class RouteDecisionNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.route_decision",
        display_name="循环或退出决策",
        category="sandbox",
        description="根据核心计算结果选择继续回环还是进入外部后处理；它是综合图中的菱形判断节点，所有出口都必须声明 when 条件并能通向结束节点。",
        version="0.1.0",
        flow_kind="decision",
    )
    CONTRACT = NodeContract(
        requires=("value.out",),
        provides=("flow.route",),
        input_semantics={"value.out": ("核心计算输出的中间数值，用来和阈值比较决定流程走向。",)},
        output_semantics={"flow.route": ("决策路由枚举；again 表示沿回环边继续处理，external 表示沿退出边进入外部后处理。",)},
        params_schema={"threshold": {"type": "number", "description": "路由判断阈值；小于该值时继续循环，大于等于该值时退出循环。"}},
        output_schema={"flow.route": {"type": "string", "enum": ["again", "external"]}},
        examples=(
            {"inputs": {"value.out": 8}, "params": {"threshold": 10}, "outputs": {"flow.route": "again"}},
            {"inputs": {"value.out": 18}, "params": {"threshold": 10}, "outputs": {"flow.route": "external"}},
        ),
    )

    def run_pure(self, inputs, params):
        return {"flow.route": "again" if inputs["value.out"] < params.get("threshold", 10) else "external"}


class LoopBackNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.loop_back",
        display_name="回环输入改写",
        category="sandbox",
        description="把本轮核心计算结果写回 value.in，作为下一轮准备阶段的输入；该节点用于验证显式回环边不会绕过 decision。",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("value.out",),
        provides=("value.in",),
        input_semantics={"value.out": ("本轮核心计算的结果，将被作为下一轮循环的原始输入。",)},
        output_semantics={"value.in": ("写回后的下一轮输入值，沿显式回环边重新进入准备节点。",)},
        output_schema={"value.in": {"type": "number"}},
        examples=({"inputs": {"value.out": 8}, "params": {}, "outputs": {"value.in": 8}},),
    )

    def run_pure(self, inputs, params):
        return {"value.in": inputs["value.out"]}


class ExternalBoostNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.external_boost",
        display_name="外部依赖后处理",
        category="sandbox",
        description="模拟项目之外维护的第三方或外部业务库；内核仍检查契约和拓扑，但不会用内部代码质量规则审计该实现。",
        version="0.1.0",
        flow_kind="process",
        external=True,
    )
    CONTRACT = NodeContract(
        requires=("value.out",),
        provides=("value.final",),
        input_semantics={"value.out": ("即将交给外部依赖处理的核心计算结果。",)},
        output_semantics={"value.final": ("外部依赖完成后处理后的最终数值，后续会被记录和输出。",)},
        params_schema={"bonus": {"type": "number", "description": "外部依赖附加的奖励值，用来模拟第三方库的业务增强。"}},
        output_schema={"value.final": {"type": "number"}},
        examples=({"inputs": {"value.out": 8}, "params": {"bonus": 5}, "outputs": {"value.final": 13}},),
    )

    def run_pure(self, inputs, params):
        return {"value.final": inputs["value.out"] + params.get("bonus", 5)}


class AuditStoreNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.audit_store",
        display_name="审计请求数据存储",
        category="sandbox",
        description="构造一条需要持久化的审计请求；在新内核中它只是数据存储形状的纯节点，不直接访问文件、数据库或网络。",
        version="0.1.0",
        flow_kind="data_store",
    )
    CONTRACT = NodeContract(
        requires=("value.final",),
        provides=("effects.request",),
        input_semantics={"value.final": ("外部后处理后的最终业务数值，需要被记录到审计请求中。",)},
        output_semantics={"effects.request": ("effects.request：结构化审计存储请求，描述应当记录的最终数值；真实写入动作由外部系统负责。",)},
        output_schema={"effects.request": {"type": "object"}},
        examples=({"inputs": {"value.final": 13}, "params": {}, "outputs": {"effects.request": {"final": 13}}},),
    )

    def run_pure(self, inputs, params):
        return {"effects.request": {"final": inputs["value.final"]}}


class ReportDocumentNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.report_document",
        display_name="生成中文报告文档",
        category="sandbox",
        description="把最终数值和审计请求组合成可输出的报告文档内容；该节点用于验证标准流程图中的 Document 文档形状。",
        version="0.1.0",
        flow_kind="document",
    )
    CONTRACT = NodeContract(
        requires=("value.final", "effects.request"),
        provides=("document.report",),
        input_semantics={"value.final": ("最终业务数值。",), "effects.request": ("包含审计字段的结构化存储请求。",)},
        output_semantics={"document.report": ("面向最终输出的报告文档正文，当前示例用字符串模拟文档内容。",)},
        output_schema={"document.report": {"type": "string"}},
        examples=(
            {
                "inputs": {"value.final": 13, "effects.request": {"final": 13}},
                "params": {},
                "outputs": {"document.report": "final=13;request=13"},
            },
        ),
    )

    def run_pure(self, inputs, params):
        return {"document.report": f"final={inputs['value.final']};request={inputs['effects.request']['final']}"}


class ReportOutputNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.report_output",
        display_name="报告输出接口",
        category="sandbox",
        description="把报告文档转换为程序对外输出；该节点验证 I/O 不是开始或结束，而是流程中的输入输出动作。",
        version="0.1.0",
        flow_kind="io",
    )
    CONTRACT = NodeContract(
        requires=("document.report",),
        provides=("io.output",),
        input_semantics={"document.report": ("已经生成的报告文档正文。",)},
        output_semantics={"io.output": ("程序最终对外暴露的输出载荷。",)},
        output_schema={"io.output": {"type": "string"}},
        examples=({"inputs": {"document.report": "final=13;request=13"}, "params": {}, "outputs": {"io.output": "final=13;request=13"}},),
    )

    def run_pure(self, inputs, params):
        return {"io.output": inputs["document.report"]}


class ReportEndNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.report_end",
        display_name="报告流程结束",
        category="sandbox",
        description="当 io.output 已经生成后终止整个综合流程；该节点证明所有非计划节点都能抵达明确的结束 Terminal。",
        version="0.1.0",
        flow_kind="terminal",
    )
    CONTRACT = NodeContract(
        requires=("io.output",),
        input_semantics={"io.output": ("综合流程最终产出的对外输出载荷。",)},
        examples=({"inputs": {"io.output": "final=13;request=13"}, "params": {}, "outputs": {}},),
    )

    def run_pure(self, inputs, params):
        return {}
