"""One neutral Host selection shared by audit, preview and native build."""
from dataclasses import replace

from vibeflow.targets.javascript.frontend.errors import ProjectBuildError
from vibeflow.tooling.project.host_extensions import host_extension_resources


def declared_hosts(config, *, catalog):
    findings = []
    resources = host_extension_resources(config, findings=findings)
    errors = [item for item in findings if str(getattr(item, "severity", "error")) == "error"]
    if errors:
        first = errors[0]
        raise ProjectBuildError("VF_AOT_HOST_EXTENSION_CONFIG",
            f"{getattr(first, 'rule_id', 'HOST_EXTENSION.CONFIG')}: {getattr(first, 'message', str(first))}")
    resolved = []
    for resource in resources:
        descriptor = catalog.get(resource.id)
        if descriptor is None:
            resolved.append(resource)
            continue
        contract = {name: tuple(getattr(descriptor, name)) for name in ("targets", "provides", "dependencies")}
        for name, expected in contract.items():
            if name in resource.declared_contract_fields and tuple(getattr(resource, name)) != expected:
                raise ProjectBuildError("VF_AOT_HOST_EXTENSION_CONFIG",
                    f"host_extension '{resource.id}' {name} must match its registered descriptor")
        resolved.append(replace(resource, display_name=resource.display_name or descriptor.display_name,
            description=resource.description or descriptor.description, version=resource.version or descriptor.version,
            **contract))
    return tuple(resolved)
