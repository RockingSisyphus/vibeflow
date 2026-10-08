#!/usr/bin/env python3
"""Observe a complete distribution using only its freshly extracted kernel."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import shutil
import sys
from zipfile import ZipFile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sandbox.adaptation_regressions.common import run_command, run_probe, row, write_json
from tools.test_parallel import add_worker_argument


PROVENANCE = r'''
import json, os, sys
from pathlib import Path
import vibeflow
from vibeflow.core.rules import RuleRecord, RuleContext
from vibeflow.targets.python.sdk import Plugin, node, rule
import vibeflow.targets.javascript.resources
expected = Path(sys.argv[1]).resolve()
origins = {name:str(Path(module.__file__).resolve()) for name,module in sys.modules.items()
           if name == "vibeflow" or name.startswith("vibeflow.") if getattr(module,"__file__",None)}
print(json.dumps({"exclusive_pythonpath":os.environ.get("PYTHONPATH")==str(expected),
 "all_kernel_origins_isolated":bool(origins) and all(Path(path).is_relative_to(expected) for path in origins.values()),
 "kernel_origins":origins,"sys_path":sys.path,"kernel_version":getattr(vibeflow,"__version__",None)}))
'''


def unpack(package: Path, work: Path):
    staged = work / "distribution"
    if package.is_dir():
        shutil.copytree(package, staged)
    else:
        with ZipFile(package) as archive:
            archive.extractall(staged)
        if not (staged / "DISTRIBUTION.json").is_file():
            candidates = tuple(staged.glob("*/DISTRIBUTION.json"))
            if len(candidates) != 1:
                raise ValueError("archive must contain one complete distribution")
            staged = candidates[0].parent
    metadata = json.loads((staged / "DISTRIBUTION.json").read_text())
    archive = staged / "kernel/vibeflow-kernel.zip"
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    kernel = work / "isolated-kernel"
    kernel.mkdir()
    with ZipFile(archive) as files:
        files.extractall(kernel)
        members = files.namelist()
    if not (kernel / "vibeflow/__init__.py").is_file():
        raise ValueError("kernel archive is missing its Python package")
    return staged, kernel, metadata, {"archive":str(archive), "sha256":digest,
        "declared_sha256":metadata.get("kernel",{}).get("sha256"), "member_count":len(members)}


def package_cases(distribution, kernel, metadata, archive, work):
    rows = [row("release.kernel.integrity", "release", "Complete package kernel matches its declared hash",
        {"matches_manifest":True}, {"matches_manifest":archive["sha256"]==archive["declared_sha256"],
        **archive}, project=distribution)]
    raw = run_probe(work / "provenance", PROVENANCE, kernel, args=[kernel], name="kernel-origins")
    origins = raw.get("payload") or {}
    rows.append(row("release.kernel.isolation", "release", "Every imported VibeFlow module comes from the extracted kernel",
        {"exit_code":0,"exclusive_pythonpath":True,"all_kernel_origins_isolated":True},
        {"exit_code":raw["exit_code"],**origins}, project=work / "provenance"))
    for command, extra in (("verify-kernel", []), ("validate", ["--config", "python_project/configs/main.jsonc", "--json"])):
        raw = run_command(distribution, [sys.executable,"-B",distribution / "run.py",command,*extra],
                          kernel, name="release-"+command)
        rows.append(row("release.launcher."+command, "release", "Original complete-package launcher: "+command,
            {"exit_code":0},raw,project=distribution))
    for relative, language in (("kernel/docs/user/python-development.md","python"),
                               ("kernel/docs/user/javascript-development.md","javascript"),
                               ("AGENTS.md","prompt")):
        path = distribution / relative
        text = path.read_text(encoding="utf-8")
        code = "RESOURCE.IMPLEMENTATION.CONFLICT"
        index = text.find(code)
        section = text[max(0,index-350):index+350] if index >= 0 else ""
        actual = {"conflict_diagnostic_documented":code in text,
                  "same_actual_source_documented":("source" in section or "源码" in section)
                      and any(term in section for term in ("同源","同一","一致","相同")),
                  "explicit_source_documented":"显式" in section,
                  "path":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"excerpt":section}
        rows.append(row("release.docs."+language, "release", "Packaged manual/prompt explains legitimate source assertions",
            {"conflict_diagnostic_documented":True,"same_actual_source_documented":True,"explicit_source_documented":True},
            actual,project=distribution))
    return rows


def isolated_observer(work):
    """Copy instrumentation, removing the development-repository import path."""
    directory = work / "observer"
    directory.mkdir()
    counters = ROOT / "sandbox/python/review_performance/counters.py"
    (directory / "observer_counters.py").write_text(counters.read_text())
    observer = Path(__file__).with_name("python_runtime_observer.py").read_text()
    observer = observer.replace('ROOT = Path(__file__).resolve().parents[2]\nsys.path.insert(0, str(ROOT))\n', '')
    observer = observer.replace('from sandbox.python.review_performance.counters import Observations',
                                'from observer_counters import Observations')
    target = directory / "python_runtime_observer.py"
    target.write_text(observer)
    return target


def core_cases(work, kernel):
    from sandbox.adaptation_regressions import core_sdk
    # Public source controls, checked runs, records and fixed contribution
    # controls retain their original case IDs and correct expectations.
    return [*core_sdk._node_identity_cases(work / "nodes",kernel),
            *core_sdk._rule_identity_cases(work / "rules",kernel),
            *core_sdk._record_cli_cases(work / "records",kernel),
            *core_sdk._contribution_cases(work / "contributions",kernel)]


def python_cases(work, kernel, observer):
    from sandbox.adaptation_regressions import python_runtime
    from sandbox.python.review_performance.fixtures import write_project
    python_runtime.OBSERVER = observer
    rows = python_runtime.compiler_cases(work / "compiler",kernel)
    project = work / "presentation"
    write_project(project,nodes=8,libraries=1,lines=350)
    argv = python_runtime.arguments(project,"export-architecture") + ["--output",str(project / "ARCHITECTURE.jsonc")]
    raw = python_runtime.counted(project,argv,kernel)
    parsed = {name:count for name,count in raw.get("parsing_counts",{}).items()
              if str(project) in name and name.endswith(".py")}
    actual = {"exit_code":raw.get("exit_code"),"error":raw.get("error"),
        "all_sources_parsed_once":bool(parsed) and all(count==1 for count in parsed.values()),
        "presentation_rechecks":sum(raw.get("presentation_calls",{}).get(name,0)
                                    for name in ("bind","compile","library_review","rule_plan")),
        "call_rule_executions":sum(item["executions"] for item in raw.get("rules",[]) if item["id"]=="perf.call"),
        "architecture_exists":(project / "ARCHITECTURE.jsonc").is_file(), "observation":raw}
    rows.append(row("release.python.performance", "performance", "Final Architecture uses checked facts without repeated preparation",
        {"exit_code":0,"error":None,"all_sources_parsed_once":True,"presentation_rechecks":0,
         "call_rule_executions":8,"architecture_exists":True},actual,project=project))
    return rows


def host_cases(work, kernel, toolchain):
    from sandbox.adaptation_regressions import js_hosts, js_lifecycle
    from sandbox.adaptation_regressions.js_fixtures import project, cli_args, cli_summary, check_cli
    from sandbox.adaptation_regressions.common import run_cli
    rows = []
    for lines, command in ((300,"build"),(501,"validate")):
        root = project(work / ("host-"+str(lines)),toolchain)
        js_hosts.child(root,lines=lines,second_file=lines==300)
        raw = js_lifecycle._build(root,kernel,toolchain) if command=="build" else run_cli(
            root,cli_args(root,command),kernel,name=command,toolchain=toolchain)
        actual = cli_summary(raw)
        accepted = lines==300
        failures = check_cli(actual,accepted=accepted,code=None if accepted else "BASE_LIB.SOURCE.MAX_LINES")
        if accepted:
            actual["native"] = js_hosts._host_execution(root,kernel,raw,toolchain)
            expected = {"exit_code":0,"number":6,"events":["child-create","child-start","child-stop"]}
            if actual["native"] != expected:
                failures.append("Host must create, start and stop one native instance and compute 6")
        rows.append(row("release.host."+str(lines),"host","Packaged multi-file Host keeps native lifecycle and per-file health",
                        {"exit_code":0 if accepted else 1},actual,failures,root))
    return rows


def javascript_cases(work, kernel, toolchain):
    from sandbox.adaptation_regressions import js_identity, js_lifecycle, js_analysis
    return [*js_identity.observe(work / "identity",kernel,toolchain,None),
            *js_lifecycle.finite_graph_cases(work / "compiler",kernel,toolchain),
            *host_cases(work / "host",kernel,toolchain),
            *js_analysis.observe(work / "analysis",kernel,toolchain,None)]


def expected_case_ids():
    manifest = json.loads(Path(__file__).with_name("cases.json").read_text())
    selected = {
        "release.kernel.integrity", "release.kernel.isolation",
        "release.launcher.verify-kernel", "release.launcher.validate",
        "release.docs.python", "release.docs.javascript", "release.docs.prompt",
        "release.python.performance", "release.host.300", "release.host.501",
    }
    for group, prefixes in (
        ("core_sdk", ("A01.node.", "A01.rule.", "A08.formal.", "S01.")),
        ("python_runtime", ("A02.python.compiler.",)),
        ("javascript", ("js.A01.", "js.A03.", "js.S02.")),
    ):
        selected.update(identifier for identifier in manifest[group] if identifier.startswith(prefixes))
    return selected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package",type=Path,required=True,help="complete distribution directory or ZIP")
    parser.add_argument("--work",type=Path,required=True,help="new directory for package, kernel and observations")
    parser.add_argument("--report",type=Path,required=True)
    parser.add_argument("--toolchain",type=Path,required=True,help="locked JS toolchain used by full verification")
    parser.add_argument("--purpose",choices=("release","script-validation"),default="release")
    add_worker_argument(parser)
    args = parser.parse_args(argv)
    args.work,args.package,args.toolchain=args.work.resolve(),args.package.resolve(),args.toolchain.resolve()
    if args.work.exists():
        parser.error("--work must be a new directory")
    args.work.mkdir(parents=True)
    rows, errors, metadata, archive, kernel = [], [], {}, {}, None
    try:
        distribution,kernel,metadata,archive=unpack(args.package,args.work)
        rows.extend(package_cases(distribution,kernel,metadata,archive,args.work))
        observer=isolated_observer(args.work)
        suites={"core_sdk":lambda:core_cases(args.work / "core",kernel),
                "python":lambda:python_cases(args.work / "python",kernel,observer),
                "javascript":lambda:javascript_cases(args.work / "javascript",kernel,args.toolchain)}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            pending={pool.submit(suite):name for name,suite in suites.items()}
            for future in as_completed(pending):
                name=pending[future]
                try:
                    found=future.result()
                    if not found:
                        raise ValueError("suite returned no observations")
                    rows.extend(found)
                    print(f"{name}: {len(found)} observations",flush=True)
                except Exception as error:
                    errors.append({"suite":name,"error":repr(error)})
                    print(f"{name}: {error!r}",flush=True)
    except Exception as error:
        errors.append({"suite":"package","error":repr(error)})
    observed = Counter(item["id"] for item in rows)
    expected = expected_case_ids()
    missing, extra = expected - observed.keys(), observed.keys() - expected
    duplicates = [identifier for identifier, count in observed.items() if count != 1]
    if missing or extra or duplicates:
        errors.append({"suite":"manifest", "error":"required release cases differ",
                       "missing":sorted(missing), "extra":sorted(extra), "duplicates":duplicates})
    counts={"cases":len(rows),"expected_cases":len(expected),"matched":sum(item["matched"] for item in rows),
            "unmatched":sum(not item["matched"] for item in rows),"observation_errors":len(errors)}
    result={"schema":"vibeflow.adaptation-release-probe.v1","purpose":args.purpose,
        "workers":args.workers,"package":str(args.package),"distribution":metadata,"kernel":archive,
        "isolated_kernel":str(kernel) if kernel else None,
        "source_boundary":"Fixture and instrumentation copies come from the sandbox; child PYTHONPATH contains only the extracted package kernel. No workspace src or original kernel is used.",
        "acceptance":args.purpose=="release" and bool(rows) and not errors and not counts["unmatched"],
        "summary":counts,"cases":sorted(rows,key=lambda item:item["id"]),"errors":errors}
    write_json(args.report.resolve(),result)
    print(counts,flush=True)
    for item in rows:
        if not item["matched"]:
            print(item["id"]+": "+"; ".join(item["failures"]),flush=True)
    return 2 if errors else int(bool(counts["unmatched"]))


if __name__=="__main__":
    raise SystemExit(main())
