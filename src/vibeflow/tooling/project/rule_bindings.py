"""Assemble governance bindings; implementations remain in their Target adapter."""
from contextlib import contextmanager, ExitStack
from collections import defaultdict

from vibeflow.targets.shared.bindings import native_binding
from vibeflow.tooling.application.project_targets import preparation_adapter


@contextmanager
def governance_rule_handlers(catalogs, *, target_root, node_command="node"):
    handlers, selected = {}, defaultdict(list)
    for rule in catalogs.rules:
        if rule.level not in {"project","root"}:
            continue
        native = native_binding(catalogs,"rule",rule.id)
        if native is not None:
            handlers[rule.id] = native
        else:
            language = "javascript" if any(item.language in {"javascript","typescript"} for item in rule.implementations) else "python"
            selected[language].append(rule)
    with ExitStack() as stack:
        for language,rules in selected.items():
            handlers.update(stack.enter_context(preparation_adapter(language).governance_handlers(
                catalogs,rules,target_root=target_root,node_command=node_command)))
        yield handlers
