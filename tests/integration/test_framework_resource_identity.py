"""Real ZIP kernels must not turn their own SDK into business resources."""
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from distribution.build import build_release


@pytest.fixture(scope="module")
def release(tmp_path_factory):
    root = tmp_path_factory.mktemp("sdk-identity-release")
    return build_release(root / "distribution", archive_dir=root / "archives", run_self_check=False)


@pytest.fixture
def project(release, tmp_path):
    root = tmp_path / "workspace"
    with zipfile.ZipFile(release.archive) as archive:
        archive.extractall(root)
    root = root / "vibeflow-distribution"
    tools = Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"])
    (root / "javascript_project/node_modules").symlink_to(tools / "node_modules", target_is_directory=True)
    rules = root / "project_rules.jsonc"
    data = json.loads(rules.read_text())
    data["rule_params"]["vibeflow.project.layout"]["directories"].append({"path":"tmp", "purpose":"Toolchain temporary files"})
    rules.write_text(json.dumps(data))
    return root


def command(root, temporary, *args, expected=0):
    temporary.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "TMPDIR":str(temporary), "TMP":str(temporary), "TEMP":str(temporary), "PYTHONDONTWRITEBYTECODE":"1"}
    env.pop("PYTHONPATH", None)
    result = subprocess.run([sys.executable, "-B", *args], cwd=root, env=env, capture_output=True, text=True)
    assert result.returncode == expected, result.stdout + result.stderr
    return result


@pytest.mark.parametrize("inside", [True, False])
@pytest.mark.parametrize("delayed", [True, False])
def test_zip_sdk_location_does_not_change_default_review_or_build(project, tmp_path, inside, delayed):
    temporary = project / "tmp" if inside else tmp_path / "outside"
    if delayed:
        plugin = project / "javascript_project/plugins/code_plugin/plugin.ts"
        plugin.write_text(plugin.read_text().replace("definePlugin,", "defineBaseLib,definePlugin,").replace(
            "resources:[", 'resources:[defineBaseLib({id:"delayed",rulesets:[],source:{kind:"file",ref:"implementation.ts",export:"value"}}),'))
        plugin.with_name("implementation.ts").write_text('import type {Json} from "@vibeflow/plugin";\nexport function value():Json{return 7;}\n')
    command(project, temporary, "run.py", "review", "--config", "javascript_project/configs/main.jsonc")
    built = tmp_path / "build"
    command(project, temporary, "run.py", "build", "--config", "javascript_project/configs/main.jsonc",
            "--target", "node", "--profile", "single-esm", "--out-dir", str(built))
    assert (built / "vibeflow-build.json").is_file()
    assert not list(temporary.glob("vibeflow-js-resources-*"))


@pytest.mark.parametrize("mode", ["same-name", "fake-directory", "symlink"])
def test_user_files_in_temporary_directory_are_still_checked(project, mode):
    temporary = project / "tmp"
    folder = temporary / "vibeflow-js-resources-user/resources" if mode == "fake-directory" else temporary
    folder.mkdir(parents=True)
    source = folder / "sdk.d.ts"
    source.write_text("export const value=1;\n")
    target = source
    if mode == "symlink":
        target = temporary / "link.ts"
        target.symlink_to(source)
    plugin = project / "javascript_project/plugins/code_plugin/plugin.ts"
    plugin.write_text('import {value} from '+json.dumps(os.path.relpath(target, plugin.parent))+';\nvoid value;\n'+plugin.read_text())
    result = command(project, temporary, "run.py", "review", "--config", "javascript_project/configs/main.jsonc", expected=1)
    assert "RESOURCE.REFERENCE.UNDECLARED" in result.stdout or "PLUGIN.PACKAGE.IMPORT" in result.stdout, result.stdout


def test_zip_raw_facts_keep_sdk_identity_across_driver_lifetimes(project):
    script = '''import json,sys
from pathlib import Path
sys.path.insert(0,str(Path("kernel/vibeflow-kernel.zip").resolve()))
from vibeflow.targets.javascript.build.toolchain import run_quality_facts_driver
from vibeflow.targets.javascript.build.driver_session import DriverScope
from vibeflow.targets.javascript.resources.identity import business_import_sites
root=Path.cwd();package=root/"javascript_project";plugin=package/"plugins/code_plugin/plugin.ts"
request={"qualityRoot":str(root),"qualityFiles":[str(plugin)]}
results=[run_quality_facts_driver(request,package_root=package)]
with DriverScope():results.append(run_quality_facts_driver(request,package_root=package))
for facts in results:
    sdk=[s for f in facts.files for s in f["import_sites"] if s["raw_import"]=="@vibeflow/plugin"]
    assert sdk and all(s["framework_resource"]=="javascript/sdk.d.ts" for s in sdk),sdk
    assert not any(s["raw_import"]=="@vibeflow/plugin" for _,s in business_import_sites(facts.files))
    assert all(not Path(s["resolved_path"]).exists() for s in sdk)
print("raw references retained; business projection excludes SDK")
'''
    command(project, project / "tmp", "-c", script)


def test_explicit_contribution_cannot_claim_a_core_file(project):
    script = '''import json,sys
from pathlib import Path
sys.path.insert(0,str(Path("kernel/vibeflow-kernel.zip").resolve()))
from vibeflow.targets.javascript.resources import materialized_resources
from vibeflow.tooling.project.workspace_loader import load_workspace_config
from vibeflow.tooling.project.preparation import ProjectPreparation
root=Path.cwd();plugin=root/"javascript_project/plugins/code_plugin/plugin.ts"
with materialized_resources() as directory:
    library='defineBaseLib({id:"claimed.core",rulesets:[],source:'+json.dumps({"kind":"file","ref":str(directory/"sdk.mjs"),"export":"definePlugin"})+'})'
    plugin.write_text(plugin.read_text().replace("definePlugin,","defineBaseLib,definePlugin,").replace("resources:[","resources:["+library+","))
    workspace=load_workspace_config(root/"vibeflow_config.jsonc")
    config=root/"javascript_project/configs/main.jsonc"
    result=ProjectPreparation(workspace,root=workspace.root_for_path(config),workflow=config).review()
    assert any(f.rule_id=="PLUGIN.PACKAGE.OWNERSHIP" for f in result.findings),[f.to_dict() for f in result.findings]
print("core identity does not authorize user contribution declarations")
'''
    command(project, project / "tmp", "-c", script)


def test_zip_resource_identity_does_not_trust_extra_files_or_symlinks(project):
    script = '''import sys
from pathlib import Path
sys.path.insert(0,str(Path("kernel/vibeflow-kernel.zip").resolve()))
from vibeflow.targets.javascript.resources import materialized_resources
from vibeflow.targets.javascript.resources.identity import FrameworkResources
with materialized_resources() as directory:
    fake=directory/"user.ts";fake.write_text("export const value=1;")
    target=Path("tmp/user-owned.ts").resolve();target.write_text("export const value=2;")
    link=directory/"alias.ts";link.symlink_to(target)
    identity=FrameworkResources(directory)
    assert identity.identify(directory/"sdk.d.ts")=="javascript/sdk.d.ts"
    assert not identity.identify(fake) and not identity.identify(link)
assert not directory.exists()
try:
    with materialized_resources() as directory:
        raise RuntimeError("check cleanup")
except RuntimeError:pass
assert not directory.exists()
print("only exact framework members identified; cleanup succeeds")
'''
    command(project, project / "tmp", "-c", script)
