"""Run Python baseline-rule observations against the caller-selected kernel.

No VibeFlow import happens while loading this module.  The parent chooses
PYTHONPATH and calls this in a separate process for each kernel variant.
"""

from pathlib import Path
import runpy


def run_cases(work_root: Path, variant: str, toolchain_root: Path | None = None) -> list[dict]:
    if variant not in {"baseline", "current"}:
        raise ValueError(f"unknown kernel variant: {variant}")
    del toolchain_root  # Python cases do not require the JavaScript toolchain.
    directory = Path(__file__).parent
    runner = runpy.run_path(str(directory / "fixture.py"))["observe"]
    specs = []
    for filename in (
        "node_specs.py", "library_specs.py", "source_specs.py", "coupling_specs.py",
        "authority_variants.py", "numeric_variants.py", "effect_variants.py",
        "ownership_variants.py", "library_variants.py", "import_variants.py",
    ):
        specs.extend(runpy.run_path(str(directory / filename))["case_specs"]())
    work_root = Path(work_root).resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    return [runner(work_root, variant, spec) for spec in specs]
