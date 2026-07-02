from __future__ import annotations

from .base_lib import BaseLibDependencySummary, BaseLibFinding, BaseLibModuleReport, BaseLibScanReport, scan_base_lib, summarize_base_lib_dependency_chain
from .architecture_report import build_architecture_report
from .config_loader import ConfigDocument, ConfigLoadError, load_config_document, strip_jsonc_comments
from .compiler import CompiledGraph, GraphCompileError, GraphCompiler
from .context import Context
from .execution_plan import CompiledBlock, ExecutionPlan, NodeFrame, build_execution_plan
from .graph_config import EdgeSpec, GraphConfig, NodeSpec, NodesetSpec, parse_graph_config
from .health import HealthFinding, HealthReport, validate_graph_health
from .ascii_flowchart import export_ascii_flowchart
from .mermaid import export_mermaid
from .mermaid_render import MermaidRenderError, is_mermaid_svg_renderer_available, render_mermaid_svg
from .node import FLOW_KINDS, FLOW_KIND_DATA_STORE, FLOW_KIND_DECISION, FLOW_KIND_DOCUMENT, FLOW_KIND_IO, FLOW_KIND_PREDEFINED, FLOW_KIND_PREPARATION, FLOW_KIND_PROCESS, FLOW_KIND_TERMINAL, NodeContract, NodeInfo, PureNode
from .node_config import NodeConfigSpec
from .policy import EffectivePolicy, PolicyResolveResult, default_effective_policy, resolve_effective_policy
from .plugin import CompilerPlugin, PluginDescriptor, PluginRegistry, PolicyPlugin, RuntimePlugin, load_plugins_from_config
from .purity import NodeMetrics, collect_node_metrics
from .registry import NodeRegistry, NodeRegistryError
from .resources import schema_text
from .runtime import PipelineRuntime, PipelineRuntimeError
from .runtime_options import HookPlan, RuntimeOptions
from .runner import CheckedRunError, CheckedRunResult, run_checked

__all__ = [
    "CompiledGraph",
    "CompiledBlock",
    "ConfigDocument",
    "ConfigLoadError",
    "Context",
    "CheckedRunError",
    "CheckedRunResult",
    "BaseLibFinding",
    "BaseLibDependencySummary",
    "BaseLibModuleReport",
    "BaseLibScanReport",
    "build_architecture_report",
    "build_execution_plan",
    "CompilerPlugin",
    "EdgeSpec",
    "EffectivePolicy",
    "ExecutionPlan",
    "GraphCompileError",
    "GraphCompiler",
    "GraphConfig",
    "MermaidRenderError",
    "FLOW_KINDS",
    "FLOW_KIND_DATA_STORE",
    "FLOW_KIND_DECISION",
    "FLOW_KIND_DOCUMENT",
    "FLOW_KIND_IO",
    "FLOW_KIND_PREDEFINED",
    "FLOW_KIND_PREPARATION",
    "FLOW_KIND_PROCESS",
    "FLOW_KIND_TERMINAL",
    "HealthFinding",
    "HealthReport",
    "HookPlan",
    "NodeContract",
    "NodeFrame",
    "NodeInfo",
    "NodeMetrics",
    "NodeConfigSpec",
    "NodeRegistry",
    "NodeRegistryError",
    "NodeSpec",
    "PluginDescriptor",
    "PluginRegistry",
    "PolicyPlugin",
    "PolicyResolveResult",
    "RuntimePlugin",
    "RuntimeOptions",
    "STABLE_PUBLIC_API",
    "NodesetSpec",
    "PipelineRuntime",
    "PipelineRuntimeError",
    "PureNode",
    "collect_node_metrics",
    "default_effective_policy",
    "export_mermaid",
    "export_ascii_flowchart",
    "is_mermaid_svg_renderer_available",
    "load_config_document",
    "load_plugins_from_config",
    "parse_graph_config",
    "resolve_effective_policy",
    "render_mermaid_svg",
    "run_checked",
    "scan_base_lib",
    "schema_text",
    "strip_jsonc_comments",
    "summarize_base_lib_dependency_chain",
    "validate_graph_health",
]

STABLE_PUBLIC_API = tuple(__all__)
