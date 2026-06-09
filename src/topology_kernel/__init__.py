from __future__ import annotations

from .base_lib import BaseLibDependencySummary, BaseLibFinding, BaseLibModuleReport, BaseLibScanReport, scan_base_lib, summarize_base_lib_dependency_chain
from .boundary import BoundaryRegistry, BoundaryRegistryError, BoundarySpec, GlobalBoundary
from .config_loader import ConfigDocument, ConfigLoadError, load_config_document, strip_jsonc_comments
from .compiler import CompiledGraph, GraphCompileError, GraphCompiler
from .context import Context
from .graph_config import EdgeSpec, GraphConfig, LoopSpec, NodeSpec, NodesetSpec, parse_graph_config
from .health import HealthFinding, HealthReport, validate_graph_health
from .mermaid import export_mermaid
from .node import NodeContract, NodeInfo, PureNode
from .node_config import NodeConfigSpec
from .policy import EffectivePolicy, PolicyResolveResult, default_effective_policy, resolve_effective_policy
from .plugin import BoundaryPlugin, CompilerPlugin, PluginDescriptor, PluginRegistry, PolicyPlugin, RuntimePlugin, load_plugins_from_config
from .purity import NodeMetrics, collect_node_metrics
from .registry import NodeRegistry, NodeRegistryError
from .resources import schema_text
from .runtime import PipelineRuntime, PipelineRuntimeError
from .runner import CheckedRunError, CheckedRunResult, run_checked

__all__ = [
    "CompiledGraph",
    "ConfigDocument",
    "ConfigLoadError",
    "Context",
    "CheckedRunError",
    "CheckedRunResult",
    "BaseLibFinding",
    "BaseLibDependencySummary",
    "BaseLibModuleReport",
    "BaseLibScanReport",
    "BoundaryRegistry",
    "BoundaryRegistryError",
    "BoundarySpec",
    "BoundaryPlugin",
    "CompilerPlugin",
    "EdgeSpec",
    "EffectivePolicy",
    "GraphCompileError",
    "GraphCompiler",
    "GraphConfig",
    "GlobalBoundary",
    "HealthFinding",
    "HealthReport",
    "LoopSpec",
    "NodeContract",
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
    "STABLE_PUBLIC_API",
    "NodesetSpec",
    "PipelineRuntime",
    "PipelineRuntimeError",
    "PureNode",
    "collect_node_metrics",
    "default_effective_policy",
    "export_mermaid",
    "load_config_document",
    "load_plugins_from_config",
    "parse_graph_config",
    "resolve_effective_policy",
    "run_checked",
    "scan_base_lib",
    "schema_text",
    "strip_jsonc_comments",
    "summarize_base_lib_dependency_chain",
    "validate_graph_health",
]

STABLE_PUBLIC_API = tuple(__all__)
