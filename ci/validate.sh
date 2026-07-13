#!/bin/bash
# CI contract validation. Default mode is a bounded, deterministic smoke test.
set -euo pipefail

if [ "$#" -gt 1 ]; then
    echo "usage: bash ci/validate.sh [--quick|--confirmation]" >&2
    exit 2
fi

ROOT="${CI_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ROOT"

MODE="${1:---quick}"
case "$MODE" in
    --quick|--confirmation) ;;
    *) echo "usage: bash ci/validate.sh [--quick|--confirmation]" >&2; exit 2 ;;
esac

run_claim_checker() {
    if [ ! -f paper/evidence/check_claims.py ]; then
        echo "claim checker missing: paper/evidence/check_claims.py" >&2
        return 3
    fi
    python3 paper/evidence/check_claims.py
}

check_golden() {
    local label="$1" output="$2" value
    value="$(printf '%s\n' "$output" | awk '
        /燃料消耗|燃料[[:space:]]*:|fuel usage/ {
            line=$0; sub(/^[^:=]*[:=][[:space:]]*/, "", line)
            if (match(line, /^[0-9]+([.][0-9]+)?/)) value=substr(line, RSTART, RLENGTH)
        } END { print value }')"
    python3 - "$label" "$value" <<'PY'
import sys
label, value = sys.argv[1:]
try:
    passed = abs(float(value) - 400.7) <= 0.5
except ValueError:
    passed = False
if not passed:
    raise SystemExit(f"{label}: invalid numerical golden result {value!r}")
print(f"{label}: {value} kg (numerical golden only)")
PY
}

run_golden_command() {
    local label="$1" output
    shift
    output="$("$@" 2>&1)" || {
        printf '%s\n' "$output" >&2
        return 1
    }
    check_golden "$label" "$output"
}

run_numerical_goldens() {
    run_golden_command "ecos_avx" ./build/bin/ecos_avx
    run_golden_command "ecos_scalar" ./build/bin/ecos_scalar
    run_golden_command "ecos_auto" ./build/bin/ecos_auto
    if [ -x build/bin/ecos_clarabel ]; then
        run_golden_command "ecos_clarabel" env LD_LIBRARY_PATH=/usr/local/lib ./build/bin/ecos_clarabel
    fi
    run_golden_command "CVXPY+ECOS" env PYTHONPATH=MarsLanding python3 -c \
        "import cvxpy as cp; from mars_solve import solve_cvxpy; f,_=solve_cvxpy(cp.ECOS); print(f'燃料: {f:.1f} kg')"
    run_golden_command "CVXPY+Clarabel" env PYTHONPATH=MarsLanding python3 -c \
        "import cvxpy as cp; from mars_solve import solve_cvxpy; f,_=solve_cvxpy(cp.CLARABEL); print(f'燃料: {f:.1f} kg')"
    run_golden_command "CasADi+IPOPT" env PYTHONPATH=MarsLanding python3 -c \
        "from mars_solve import solve_ipopt; f,_=solve_ipopt(); print(f'燃料: {f:.1f} kg')"
}

run_quick() {
    run_claim_checker
    python3 -m unittest discover -s tests
    python3 MarsLanding/check_model_consistency.py
    python3 -m unittest tests.test_handwritten_asset
    run_numerical_goldens

    local work results
    work="$(mktemp -d)"
    trap 'rm -rf "$work"' RETURN
    results="$work/contract-smoke.jsonl"
    python3 -m experiments.run_monte_carlo \
        --scenario experiments/scenarios/near_nominal_v1.json \
        --output "$results" --count 8
    python3 - "$results" <<'PY'
import json
import sys
from pathlib import Path
from experiments.contracts import validate_result

records = []
for line_number, line in enumerate(Path(sys.argv[1]).read_text(encoding="utf-8").splitlines(), 1):
    if not line.strip():
        raise SystemExit(f"blank JSONL line: {line_number}")
    record = json.loads(line)
    validate_result(record)
    records.append(record)
if len(records) != 8:
    raise SystemExit(f"contract smoke expected 8 records, got {len(records)}")
PY
}

run_confirmation() {
    # CI validates frozen artifacts; it never regenerates the authoritative run.
    run_claim_checker
    local manifest="experiments/scenarios/near_nominal_v1.json"
    local results="experiments/results/near_nominal_v1.jsonl"
    local compressed="experiments/results/near_nominal_v1.jsonl.gz"
    local summary="experiments/results/near_nominal_v1.summary.json"
    local ledger="paper/evidence/claims.json"
    local work recomputed

    for path in "$manifest" "$results" "$compressed" "$summary" "$ledger"; do
        if [ ! -f "$path" ]; then
            echo "confirmation unavailable: frozen evidence missing: $path" >&2
            exit 3
        fi
    done
    python3 - "$manifest" "$results" "$compressed" "$summary" "$ledger" <<'PY'
import gzip
import hashlib
import json
import sys
from pathlib import Path
from experiments.contracts import validate_result

manifest, raw_path, gzip_path, summary_path, ledger_path = map(Path, sys.argv[1:])
RAW_LIMIT = 16 * 1024 * 1024
GZIP_LIMIT = 4 * 1024 * 1024
LINE_LIMIT = 1 * 1024 * 1024
CHUNK = 64 * 1024

if raw_path.stat().st_size > RAW_LIMIT:
    raise SystemExit("frozen JSONL exceeds 16 MiB limit")
if gzip_path.stat().st_size > GZIP_LIMIT:
    raise SystemExit("frozen gzip exceeds 4 MiB limit")

def sha256_stream(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()

claims = json.loads(ledger_path.read_text(encoding="utf-8"))
claim = next((item for item in claims if item.get("claim_id") == "mc-status"), None)
if claim is None or claim.get("status") != "verified":
    raise SystemExit("confirmation unavailable: mc-status is not verified in claim ledger")
expected = {
    manifest: claim.get("manifest_sha256"),
    raw_path: claim.get("raw_sha256"),
    gzip_path: claim.get("gzip_sha256"),
    summary_path: claim.get("source_sha256"),
}
for path, digest in expected.items():
    if not isinstance(digest, str) or len(digest) != 64:
        raise SystemExit(f"confirmation unavailable: missing frozen sha256 for {path}")
    actual = sha256_stream(path)
    if actual != digest.lower():
        raise SystemExit(f"sha256 mismatch for {path}: expected {digest}, got {actual}")

decompressed_size = 0
with raw_path.open("rb") as raw_stream, gzip.GzipFile(filename=gzip_path) as gz_stream:
    while True:
        raw_chunk = raw_stream.read(CHUNK)
        gzip_chunk = gz_stream.read(CHUNK)
        decompressed_size += len(gzip_chunk)
        if decompressed_size > RAW_LIMIT:
            raise SystemExit("gzip decompressed data exceeds 16 MiB limit")
        if raw_chunk != gzip_chunk:
            raise SystemExit("gzip artifact does not expand byte-for-byte to frozen JSONL")
        if not raw_chunk:
            break
records = []
with raw_path.open("rb") as stream:
    for line_number, raw_line in enumerate(stream, 1):
        if len(raw_line) > LINE_LIMIT:
            raise SystemExit(f"JSONL line exceeds 1 MiB limit: {line_number}")
        if not raw_line.strip():
            raise SystemExit(f"blank JSONL line: {line_number}")
        record = json.loads(raw_line)
        validate_result(record)
        records.append(record)
if len(records) != 1000:
    raise SystemExit(f"confirmation expected 1000 records, got {len(records)}")
manifest_digest = sha256_stream(manifest)
if any(record["provenance"]["manifest_sha256"].lower() != manifest_digest
       for record in records):
    raise SystemExit("result manifest digest does not match frozen scenario manifest")
PY
    work="$(mktemp -d)"
    trap 'rm -rf "$work"' RETURN
    recomputed="$work/summary.json"
    python3 -m experiments.aggregate_results "$results" "$recomputed"
    diff -u "$summary" "$recomputed"
}

if [ "$MODE" = "--confirmation" ]; then
    run_confirmation
else
    run_quick
fi
