#!/usr/bin/env bash
# Run after the fresh official full gate completed; keep the original matrices.
# Product code comes only from its fresh wheel or profile kernel. Script inputs
# come from project docs, so discarded ignored dist files cannot break replay.
set -u
vf_old_gate=${1:?Pass the fresh official full gate completed directory}
vf_old_repo=/home/rockingsisyphus/projects/VibeFlow
vf_old_evidence=$vf_old_repo/docs/maintainers/python-alias-facts-fix-20261008
vf_old_work=$vf_old_repo/dist/python-alias-facts-validation-20261008/old-package-probes
export TMPDIR=/home/rockingsisyphus/.cache/vf-p2/t
if [[ -e $vf_old_work || -e $vf_old_evidence/old-probe-exits.tsv ]]; then
    printf '%s\n' 'Old-matrix outputs already exist; preserve them and select a fresh run.' >&2
    exit 2
fi
mkdir -p "$vf_old_work" "$TMPDIR"
if ! python -I -B -c 'import os, pathlib, tempfile; assert pathlib.Path(tempfile.gettempdir()).resolve() == pathlib.Path(os.environ["TMPDIR"]).resolve(), "selected TMPDIR is unusable; refusing a fallback"'; then
    exit 2
fi
run_old_probe() {
    vf_old_name=$1
    shift
    if "$@" > "$vf_old_work/$vf_old_name.log" 2>&1; then
        printf '%s\t0\n' "$vf_old_name" >> "$vf_old_evidence/old-probe-exits-$vf_old_profile.tsv"
    else
        vf_old_exit=$?
        printf '%s\t%s\n' "$vf_old_name" "$vf_old_exit" >> "$vf_old_evidence/old-probe-exits-$vf_old_profile.tsv"
        vf_old_status=1
    fi
}
run_old_product() {
    local vf_old_profile=$1
    local vf_old_status=0
    local vf_old_python=python
    local -a vf_old_select=()
    if [[ $vf_old_profile == wheel ]]; then
        vf_old_python=$vf_old_gate/wheel-venv/bin/python
    elif [[ $vf_old_profile == collaborative ]]; then
        vf_old_select=(--kernel "$vf_old_gate/distribution/kernel/vibeflow-kernel.zip")
    else
        vf_old_select=(--kernel "$vf_old_gate/distribution-autonomous/kernel/vibeflow-kernel.zip")
    fi
    run_old_probe "F01-original40-$vf_old_profile" "$vf_old_python" -I -B "$vf_old_evidence/replay_historical_scope.py" "${vf_old_select[@]}" \
        --review F01 --report "$vf_old_evidence/F01-original40-$vf_old_profile.json" --origin-report "$vf_old_evidence/F01-original40-$vf_old_profile-origin.json"
    run_old_probe "F02-original180-$vf_old_profile" "$vf_old_python" -I -B "$vf_old_evidence/replay_historical_scope.py" "${vf_old_select[@]}" \
        --review F02 --report "$vf_old_evidence/F02-original180-$vf_old_profile.json" --origin-report "$vf_old_evidence/F02-original180-$vf_old_profile-origin.json"
    run_old_probe "F01-formal72-$vf_old_profile" "$vf_old_python" -I -B "$vf_old_repo/docs/maintainers/python-function-definition-scope-fix-20261008/default_scope_probe.py" "${vf_old_select[@]}" \
        --work "$vf_old_work/F01-formal72-$vf_old_profile" --report "$vf_old_evidence/F01-formal72-$vf_old_profile.json" --expect fixed
    run_old_probe "F02-formal89-$vf_old_profile" "$vf_old_python" -I -B "$vf_old_repo/docs/maintainers/python-comprehension-scope-fix-20261008/comprehension_cli_probe.py" "${vf_old_select[@]}" \
        --work "$vf_old_work/F02-formal89-$vf_old_profile" --report "$vf_old_evidence/F02-formal89-$vf_old_profile.json" --expect fixed
    run_old_probe "declared34-$vf_old_profile" "$vf_old_python" -I -B "$vf_old_repo/docs/maintainers/python-comprehension-scope-fix-20261008/declared_binding_probe.py" "${vf_old_select[@]}" \
        --report "$vf_old_evidence/declared34-$vf_old_profile.json" --expect fixed
    run_old_probe "effects873-$vf_old_profile" "$vf_old_python" -I -B "$vf_old_evidence/packaged_python_effects_probe.py" "${vf_old_select[@]}" \
        --reject-source-prefix "$vf_old_repo/src" --workdir "$vf_old_work/effects873-$vf_old_profile" --report "$vf_old_evidence/effects873-$vf_old_profile.json"
    run_old_probe "inputs20-$vf_old_profile" "$vf_old_python" -I -B "$vf_old_evidence/packaged_inputs_probe.py" "${vf_old_select[@]}" \
        --work "$vf_old_work/inputs20-$vf_old_profile" --report "$vf_old_evidence/inputs20-$vf_old_profile.json"
    run_old_probe "javascript33-$vf_old_profile" "$vf_old_python" -I -B "$vf_old_evidence/packaged_js_probe.py" "${vf_old_select[@]}" \
        --toolchain-root "$vf_old_gate/pytest/javascript-toolchain" --work-root "$vf_old_work/javascript33-$vf_old_profile" --report "$vf_old_evidence/javascript33-$vf_old_profile.json"
    return "$vf_old_status"
}
vf_old_pids=()
for vf_old_profile in wheel collaborative autonomous; do
    run_old_product "$vf_old_profile" &
    vf_old_pids+=("$!")
done
vf_old_status=0
for vf_old_pid in "${vf_old_pids[@]}"; do
    if ! wait "$vf_old_pid"; then vf_old_status=1; fi
done
cat "$vf_old_evidence/old-probe-exits-wheel.tsv" \
    "$vf_old_evidence/old-probe-exits-collaborative.tsv" \
    "$vf_old_evidence/old-probe-exits-autonomous.tsv" > "$vf_old_evidence/old-probe-exits.tsv"
exit "$vf_old_status"
