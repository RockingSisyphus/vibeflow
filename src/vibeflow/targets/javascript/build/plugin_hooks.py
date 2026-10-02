"""Build-time JavaScript Compiler Plugin lifecycle orchestration."""

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
    annotations: tuple[Mapping[str, object], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "annotations": [dict(item) for item in self.annotations],
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
        self._annotations: list[Mapping[str, object]] = []

    def __enter__(self) -> JavascriptBuildPluginRunner:
        session = JavascriptPluginSession(
            node_command=self.node_command
        ).__enter__()
        self._session = session
        try:
            bindings = self.plan.compiler_plugins
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

    def report(self) -> JavascriptBuildPluginReport:
        return JavascriptBuildPluginReport(
            annotations=tuple(self._annotations),
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
        if "findings" in returned or "relaxations" in returned:
            raise JavascriptPluginError("VF_PLUGIN_HOOK_RESULT", "Compiler lifecycle hooks cannot return rule findings or relaxations; use a Rule")
        self._collect_annotations(
            binding,
            hook,
            returned.get("annotations", returned.get("annotation", ())),
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
