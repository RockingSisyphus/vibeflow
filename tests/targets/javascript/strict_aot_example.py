from __future__ import annotations

from pathlib import Path
import os
import shutil

from vibeflow.tooling.application.javascript.build import (
    ProjectBuildRequest,
    prepare_project_build,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE_ROOT = REPOSITORY_ROOT / "sandbox" / "javascript" / "minimal"


def test_minimal_js_aot_example_prepares_without_importing_business_modules(
    tmp_path: Path,
) -> None:
    example = tmp_path / "example"
    shutil.copytree(EXAMPLE_ROOT, example, ignore=shutil.ignore_patterns("node_modules", "__pycache__"))
    toolchain = Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"])
    (example / "project/node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    prepared = prepare_project_build(
        ProjectBuildRequest(
            workspace=example / "vibeflow_config.jsonc",
            config=example / "project/configs/greeting.jsonc",
            out_dir=tmp_path / "dist",
            target="browser",
            profile="web-app",
            html_template=example / "project/web/index.template.html",
            app_entry=example / "project/web/app.ts",
        )
    )

    assert prepared.used_node_ids == ("example.greet",)
    assert prepared.used_base_libs == ("example.text",)
    assert prepared.used_capabilities == ("example.clock",)
    assert prepared.plan.inputs[0].required is True
    assert prepared.plan.outputs[0].as_key == "greeting"
    assert (prepared.package_root / "package-lock.json").is_file()
    assert prepared.import_policy["node_base_libs"] == {
        "example.greet": ["example.text"]
    }


# Publish controlled case inputs as fixed SDK plugins before formal entrypoints.
