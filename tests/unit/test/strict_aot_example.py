from __future__ import annotations

from pathlib import Path

from vibeflow.aot.project_build import (
    ProjectBuildRequest,
    prepare_project_build,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE_ROOT = REPOSITORY_ROOT / "examples" / "js_aot_minimal"


def test_minimal_js_aot_example_prepares_without_importing_business_modules(
    tmp_path: Path,
) -> None:
    prepared = prepare_project_build(
        ProjectBuildRequest(
            workspace=EXAMPLE_ROOT / "vibeflow_config.jsonc",
            config=EXAMPLE_ROOT / "project/configs/greeting.jsonc",
            out_dir=tmp_path / "dist",
            target="browser",
            profile="web-app",
            html_template=EXAMPLE_ROOT / "project/web/index.template.html",
            app_entry=EXAMPLE_ROOT / "project/web/app.ts",
        )
    )

    assert prepared.used_node_types == ("example.greet",)
    assert prepared.used_base_libs == ("example.text",)
    assert prepared.used_capabilities == ("example.clock",)
    assert prepared.plan.inputs[0].required is True
    assert prepared.plan.outputs[0].as_key == "greeting"
    assert (prepared.package_root / "package-lock.json").is_file()
    assert prepared.import_policy["node_base_libs"] == {
        "example.greet": ["example.text"]
    }
