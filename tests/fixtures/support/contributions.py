"""Portable wire-data fixtures for Core Descriptor normalization tests."""
import json
from pathlib import Path

from vibeflow.core.descriptors import ContributionBuilder, ResourceOrigin, compose_contributions
from vibeflow.core.descriptors.decode import decode_resource
from vibeflow.tooling.project.descriptor_loader import DescriptorLoadError


def collected_fixture_catalogs(root, paths):
    """Test inputs become pure-memory contributions; Target loading is tested separately."""
    builders = []
    for refs in paths.values():
        for ref in refs:
            for path in sorted((Path(root) / ref).rglob("*.jsonc")):
                builder = ContributionBuilder(str(path), source=str(path))
                builder.add(decode_resource(json.loads(path.read_text().removeprefix("// descriptor fixture\n"))),
                    origin=ResourceOrigin(str(path), str(path)))
                builders.append(builder.finish())
    try:
        return compose_contributions(tuple(builders))
    except Exception as exc:
        raise DescriptorLoadError(exc.code, exc.message, exc.source,
            details={"previous_source":exc.previous_source, **exc.details}) from exc
