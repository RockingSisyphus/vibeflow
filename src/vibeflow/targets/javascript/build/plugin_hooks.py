"""Build-time JavaScript Policy and Compiler Plugin orchestration."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from pathlib import PurePath
import sys
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from vibeflow.targets.javascript.build.plugin_session import (
    JavascriptPluginError,
    JavascriptPluginSession,
)
from vibeflow.targets.javascript.frontend.bindings import (
    JavascriptPluginBinding,
)
from vibeflow.targets.javascript.frontend.plugin_descriptors import (
    JavascriptPluginBindingPlan,
)


_GRAPH_MUTATION_KEYS = frozenset(
    {"graph", "workflow", "nodes", "nodesets", "routes", "edges", "replace"}
)


@dataclass(frozen=True)
class JavascriptBuildPluginReport:
    findings: tuple[Mapping[str, object], ...] = ()
    annotations: tuple[Mapping[str, object], ...] = ()
    relaxations: tuple[Mapping[str, object], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "findings": [dict(item) for item in self.findings],
            "annotations": [dict(item) for item in self.annotations],
            "relaxations": [dict(item) for item in self.relaxations],
        }


class JavascriptBuildPluginRunner:
    """Keep build-time plugin instances alive across ordered hook phases."""

    def __init__(
        self,
        plan: JavascriptPluginBindingPlan,
        *,
        package_root: str | PurePath,
        target: str,
        workflow_id: str,
        node_command: str = "node",
    ) -> None:
        if not isinstance(plan, JavascriptPluginBindingPlan):
            raise TypeError("plan must be a JavascriptPluginBindingPlan")
        self.plan = plan
        self.package_root = str(package_root)
        self.target = str(target)
        self.workflow_id = str(workflow_id)
        self.node_command = str(node_command)
        self._session: JavascriptPluginSession | None = None
        self._ids: dict[str, str] = {}
        self._findings: list[Mapping[str, object]] = []
        self._annotations: list[Mapping[str, object]] = []
        self._relaxations: list[Mapping[str, object]] = []

    def __enter__(self) -> JavascriptBuildPluginRunner:
        session = JavascriptPluginSession(
            node_command=self.node_command
        ).__enter__()
        self._session = session
        try:
            bindings = (*self.plan.policy_plugins, *self.plan.compiler_plugins)
            for index, binding in enumerate(bindings):
                session_id = f"{binding.plugin_type}:{index}:{binding.id}"
                session.open(
                    session_id,
                    plugin=binding.to_dict(),
                    package_root=self.package_root,
                    target=self.target,
                    workflow_id=self.workflow_id,
                )
                self._ids[binding.id] = session_id
        except Exception:
            session.__exit__(*sys.exc_info())
            self._session = None
            raise
        return self

    def validate_policy(self, graph: object) -> None:
        projection = json_projection(graph)
        assert isinstance(projection, Mapping)
        for binding in self.plan.policy_plugins:
            self._invoke(
                binding,
                "extendPolicy",
                {
                    "policy": {
                        "coreErrorsNonDowngradable": True,
                        "target": self.target,
                    }
                },
            )
            nodes = projection.get("nodes", ())
            if isinstance(nodes, Sequence) and not isinstance(nodes, str):
                for node in nodes:
                    self._invoke(binding, "validateNode", {"node": node})
            nodesets = projection.get("nodesets", {})
            if isinstance(nodesets, Mapping):
                for nodeset_id in sorted(str(key) for key in nodesets):
                    self._invoke(
                        binding,
                        "validateNodeset",
                        {"id": nodeset_id, "nodeset": nodesets[nodeset_id]},
                    )
            self._invoke(binding, "validateGraph", {"graph": projection})

    def before_compile(self, graph: object) -> None:
        projection = json_projection(graph)
        for binding in self.plan.compiler_plugins:
            self._invoke(
                binding,
                "beforeCompile",
                {"graph": projection},
            )

    def after_compile(self, graph: object, compiled: object) -> None:
        payload = {
            "graph": json_projection(graph),
            "compiled": json_projection(compiled),
        }
        for binding in self.plan.compiler_plugins:
            self._invoke(binding, "afterCompile", payload)
            self._invoke(binding, "validateCompiledGraph", payload)

    def report(self) -> JavascriptBuildPluginReport:
        return JavascriptBuildPluginReport(
            findings=tuple(self._findings),
            annotations=tuple(self._annotations),
            relaxations=tuple(self._relaxations),
        )

    def __exit__(self, exc_type, exc, traceback) -> None:
        session = self._session
        self._session = None
        if session is not None:
            session.__exit__(exc_type, exc, traceback)

    def _invoke(
        self,
        binding: JavascriptPluginBinding,
        hook: str,
        payload: Mapping[str, object],
    ) -> None:
        session = self._session
        if session is None:
            raise JavascriptPluginError(
                "VF_PLUGIN_PROCESS",
                "JavaScript build plugin runner is not active",
            )
        result = session.invoke(self._ids[binding.id], hook, payload)
        if not result.implemented or result.result is None:
            return
        if not isinstance(result.result, Mapping):
            raise JavascriptPluginError(
                "VF_PLUGIN_HOOK_RESULT",
                f"plugin '{binding.id}' hook '{hook}' must return an object or null",
            )
        returned = dict(result.result)
        mutation_keys = sorted(_GRAPH_MUTATION_KEYS.intersection(returned))
        if mutation_keys:
            raise JavascriptPluginError(
                "VF_PLUGIN_HOOK_RESULT",
                f"plugin '{binding.id}' hook '{hook}' attempted to mutate the graph: {mutation_keys}",
            )
        self._collect_findings(binding, hook, returned.get("findings", ()))
        self._collect_annotations(
            binding,
            hook,
            returned.get("annotations", returned.get("annotation", ())),
        )
        if hook == "extendPolicy":
            self._collect_relaxations(
                binding,
                returned.get("relaxations", ()),
            )
            policy = returned.get("policy")
            if isinstance(policy, Mapping) and any(
                str(key) in {
                    "disableCoreErrors",
                    "removeCoreFinding",
                    "allowInvalidGraph",
                }
                for key in policy
            ):
                raise JavascriptPluginError(
                    "VF_PLUGIN_POLICY",
                    f"plugin '{binding.id}' attempted to disable a non-downgradable Core error",
                )

    def _collect_findings(
        self,
        binding: JavascriptPluginBinding,
        hook: str,
        value: object,
    ) -> None:
        for finding in _mapping_items(value, subject="findings"):
            normalized = {
                "plugin_id": binding.id,
                "plugin_type": binding.plugin_type,
                "hook": hook,
                **finding,
            }
            self._findings.append(MappingProxyType(normalized))
            if str(finding.get("severity", "info")).lower() == "error":
                raise JavascriptPluginError(
                    "VF_PLUGIN_POLICY"
                    if binding.plugin_type == "policy"
                    else "VF_PLUGIN_COMPILE",
                    str(
                        finding.get(
                            "message",
                            f"plugin '{binding.id}' rejected the build",
                        )
                    ),
                )

    def _collect_annotations(
        self,
        binding: JavascriptPluginBinding,
        hook: str,
        value: object,
    ) -> None:
        if value in (None, (), []):
            return
        values = [value] if isinstance(value, Mapping) else value
        for annotation in _mapping_items(values, subject="annotations"):
            self._annotations.append(
                MappingProxyType(
                    {
                        "plugin_id": binding.id,
                        "plugin_type": binding.plugin_type,
                        "hook": hook,
                        **annotation,
                    }
                )
            )

    def _collect_relaxations(
        self,
        binding: JavascriptPluginBinding,
        value: object,
    ) -> None:
        for relaxation in _mapping_items(value, subject="relaxations"):
            required = {"rule", "scope", "reason"}
            if not required.issubset(relaxation):
                raise JavascriptPluginError(
                    "VF_PLUGIN_POLICY",
                    f"plugin '{binding.id}' relaxation must declare rule, scope, and reason",
                )
            rule = str(relaxation.get("rule", ""))
            if rule.startswith(("CORE.", "VF_")):
                raise JavascriptPluginError(
                    "VF_PLUGIN_POLICY",
                    f"plugin '{binding.id}' cannot relax non-downgradable rule '{rule}'",
                )
            self._relaxations.append(
                MappingProxyType({"plugin_id": binding.id, **relaxation})
            )


def _mapping_items(value: object, *, subject: str) -> tuple[dict[str, object], ...]:
    if value in (None, (), []):
        return ()
    if isinstance(value, Mapping):
        values: Sequence[object] = (value,)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        values = value
    else:
        raise JavascriptPluginError(
            "VF_PLUGIN_HOOK_RESULT",
            f"plugin {subject} must be an object or list of objects",
        )
    if not all(isinstance(item, Mapping) for item in values):
        raise JavascriptPluginError(
            "VF_PLUGIN_HOOK_RESULT",
            f"plugin {subject} must contain only objects",
        )
    return tuple(dict(item) for item in values)  # type: ignore[arg-type]


def json_projection(value: object) -> object:
    """Convert Core/Block dataclasses into a frozen-worker JSON projection."""

    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, PurePath):
        return str(value)
    if isinstance(value, Mapping):
        return {
            str(key): json_projection(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list, set, frozenset)):
        items = value
        if isinstance(value, (set, frozenset)):
            items = sorted(value, key=str)
        return [json_projection(item) for item in items]
    if is_dataclass(value):
        return {
            field.name: json_projection(getattr(value, field.name))
            for field in fields(value)
        }
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return json_projection(to_dict())
    raise JavascriptPluginError(
        "VF_PLUGIN_HOOK_RESULT",
        f"cannot project {type(value).__name__} into build-plugin JSON",
    )


__all__ = [
    "JavascriptBuildPluginReport",
    "JavascriptBuildPluginRunner",
    "json_projection",
]
