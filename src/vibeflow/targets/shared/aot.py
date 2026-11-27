"""Shared artifact records, metadata and staged directory publication."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile

from vibeflow.targets.shared.aot_publish import AotPublishError, atomic_publish_directory

BUILD_MANIFEST_FORMAT = 'vibeflow.aot-build.v6'


@dataclass(frozen=True)
class BuildResult:
    out_dir: Path
    entry: Path
    manifest: Path
    toolchain: object
    files: tuple[str, ...]


def artifact_manifest(staging, *, workflow, project_target, entry, plan_sha256, target_metadata,
                      manifest_format=BUILD_MANIFEST_FORMAT):
    return dict(format=manifest_format, abi_version=workflow.abi_version,
        project_target=project_target, workflow_id=workflow.workflow_id,
        entry_mode=workflow.entry_mode, entry=entry, plan_sha256=plan_sha256,
        target_metadata=target_metadata,
        files={p.relative_to(staging).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(staging.rglob('*')) if p.is_file()})


@contextmanager
def staged_build(out_dir, *, replace=False, manifest_format=BUILD_MANIFEST_FORMAT):
    output = Path(out_dir).expanduser().absolute()
    if not replace and os.path.lexists(output):
        raise AotPublishError("VF_BUILD_EXISTS", f"output directory already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.' + output.name + '.aot-', dir=output.parent) as temporary:
        staging = Path(temporary) / 'dist'
        staging.mkdir()
        yield staging
        atomic_publish_directory(staging, output, replace=replace, manifest_format=manifest_format)


def write_manifest(staging, manifest):
    (staging / 'vibeflow-build.json').write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
