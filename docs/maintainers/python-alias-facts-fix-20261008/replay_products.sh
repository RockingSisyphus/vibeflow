#!/usr/bin/env bash
# Run after the fresh official full gate completed.
# All three products use the same strict fixed matrix. Historical 36-case output
# stays raw and its ordinary unknown-I/O exceptions are separately classified.
set -u
vf_alias_gate=${1:?Pass the fresh official full gate completed directory}
vf_alias_repo=/home/rockingsisyphus/projects/VibeFlow
vf_alias_evidence=$vf_alias_repo/docs/maintainers/python-alias-facts-fix-20261008
vf_alias_work=$vf_alias_repo/dist/python-alias-facts-validation-20261008/package-probes
export TMPDIR=/home/rockingsisyphus/.cache/vf-p2/t
if [[ -e $vf_alias_work || -e $vf_alias_evidence/package-probe-exits.tsv ]]; then
    printf '%s\n' 'Package probe outputs already exist; preserve them and select a fresh run.' >&2
    exit 2
fi
mkdir -p "$vf_alias_work" "$TMPDIR"
if ! python -I -B -c 'import os, pathlib, tempfile; assert pathlib.Path(tempfile.gettempdir()).resolve() == pathlib.Path(os.environ["TMPDIR"]).resolve(), "selected TMPDIR is unusable; refusing a fallback"'; then
    exit 2
fi
run_product() {
    local vf_alias_profile=$1
    local vf_alias_status=0
    local vf_alias_python=python
    local -a vf_alias_select=()
    if [[ $vf_alias_profile == wheel ]]; then
        vf_alias_python=$vf_alias_gate/wheel-venv/bin/python
    elif [[ $vf_alias_profile == collaborative ]]; then
        vf_alias_select=(--kernel "$vf_alias_gate/distribution/kernel/vibeflow-kernel.zip")
    else
        vf_alias_select=(--kernel "$vf_alias_gate/distribution-autonomous/kernel/vibeflow-kernel.zip")
    fi
    if "$vf_alias_python" -I -B "$vf_alias_evidence/alias_facts_probe.py" "${vf_alias_select[@]}" \
        --work "$vf_alias_work/$vf_alias_profile" --report "$vf_alias_evidence/packaged-$vf_alias_profile.json" --expect fixed \
        > "$vf_alias_work/$vf_alias_profile.log" 2>&1; then
        printf 'formal-%s\t0\n' "$vf_alias_profile" > "$vf_alias_evidence/package-probe-exits-$vf_alias_profile.tsv"
    else
        vf_alias_exit=$?
        printf 'formal-%s\t%s\n' "$vf_alias_profile" "$vf_alias_exit" > "$vf_alias_evidence/package-probe-exits-$vf_alias_profile.tsv"
        vf_alias_status=1
    fi
    if "$vf_alias_python" -I -B "$vf_alias_evidence/replay_original_alias_review.py" "${vf_alias_select[@]}" \
        --report "$vf_alias_evidence/legacy36-$vf_alias_profile.json" \
        --origin-report "$vf_alias_evidence/legacy36-$vf_alias_profile-origin.json" \
        > "$vf_alias_work/legacy36-$vf_alias_profile.log" 2>&1; then
        printf 'legacy36-%s\t0\n' "$vf_alias_profile" >> "$vf_alias_evidence/package-probe-exits-$vf_alias_profile.tsv"
    else
        vf_alias_exit=$?
        printf 'legacy36-%s\t%s\n' "$vf_alias_profile" "$vf_alias_exit" >> "$vf_alias_evidence/package-probe-exits-$vf_alias_profile.tsv"
        vf_alias_status=1
    fi
    if "$vf_alias_python" -I -B "$vf_alias_evidence/packaged_writeback103_probe.py" "${vf_alias_select[@]}" \
        --report "$vf_alias_evidence/writeback103-$vf_alias_profile.json" \
        > "$vf_alias_work/writeback103-$vf_alias_profile.log" 2>&1; then
        printf 'writeback103-%s\t0\n' "$vf_alias_profile" >> "$vf_alias_evidence/package-probe-exits-$vf_alias_profile.tsv"
    else
        vf_alias_exit=$?
        printf 'writeback103-%s\t%s\n' "$vf_alias_profile" "$vf_alias_exit" >> "$vf_alias_evidence/package-probe-exits-$vf_alias_profile.tsv"
        vf_alias_status=1
    fi
    for vf_alias_review in evaluation12 nested_clear3 writeback_exits3 writeback_exits5; do
        if "$vf_alias_python" -I -B "$vf_alias_evidence/replay_input_evaluation_review.py" "${vf_alias_select[@]}" \
            --review "$vf_alias_review" --expect fixed --report "$vf_alias_evidence/$vf_alias_review-$vf_alias_profile.json" \
            > "$vf_alias_work/$vf_alias_review-$vf_alias_profile.log" 2>&1; then
            printf '%s-%s\t0\n' "$vf_alias_review" "$vf_alias_profile" >> "$vf_alias_evidence/package-probe-exits-$vf_alias_profile.tsv"
        else
            vf_alias_exit=$?
            printf '%s-%s\t%s\n' "$vf_alias_review" "$vf_alias_profile" "$vf_alias_exit" >> "$vf_alias_evidence/package-probe-exits-$vf_alias_profile.tsv"
            vf_alias_status=1
        fi
    done
    return "$vf_alias_status"
}
vf_alias_pids=()
for vf_alias_profile in wheel collaborative autonomous; do
    run_product "$vf_alias_profile" &
    vf_alias_pids+=("$!")
done
vf_alias_status=0
for vf_alias_pid in "${vf_alias_pids[@]}"; do
    if ! wait "$vf_alias_pid"; then vf_alias_status=1; fi
done
cat "$vf_alias_evidence/package-probe-exits-wheel.tsv" \
    "$vf_alias_evidence/package-probe-exits-collaborative.tsv" \
    "$vf_alias_evidence/package-probe-exits-autonomous.tsv" > "$vf_alias_evidence/package-probe-exits.tsv"
exit "$vf_alias_status"
