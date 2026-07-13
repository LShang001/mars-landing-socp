#!/usr/bin/env python3
"""校验论文 claim ledger，并阻止已撤回数字重新进入正文。"""

import json
import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LEDGER = Path(__file__).with_name("claims.json")
REQUIRED = {
    "claim_id", "manuscript_files", "value", "scope", "source", "command", "status"
}
STATUSES = {"verified", "superseded", "future_work"}
SUPERSEDED_TEXT = ("401.2 kg", "8.3 kg", "8 microseconds", "8 $\\mu$s")
MANUSCRIPT_FILES = (
    "paper/mars_landing_socp.tex",
    "paper/chapters/ch1_intro.tex",
    "paper/chapters/ch4_sparse_ecos.tex",
    "paper/chapters/ch5_results.tex",
    "paper/chapters/ch6_embedded.tex",
    "paper/chapters/ch7_conclusion.tex",
)
OVERSTRONG_TEXT = (
    "六种求解",
    "六方案",
    "六求解器",
    "严格一致",
    "全部收敛",
    "验证了无损凸化",
    "证明了本文手写",
    "证实了 SOCP 建模的正确性",
    "裸机环境",
    "不依赖任何商业或外部",
    "可直接运行于资源受限",
    "具有普遍意义",
    "必须在硬件层面支持双精度",
    "自动微分路径的对比",
    "内存带宽瓶颈",
    "Cortex-A72 处理器上单次求解约需",
    "LDL 分解约占求解时间的 60\\%--70\\%",
)


def load_claims(path=LEDGER):
    claims = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(claims, list):
        raise ValueError("claim ledger root must be a JSON array")
    return claims


def _repo_path(value):
    path = Path(value)
    return ROOT / path


def _valid_repo_relative(value):
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return False
    try:
        (ROOT / path).resolve().relative_to(ROOT.resolve())
    except ValueError:
        return False
    return True


def scan_manuscript_language(paths=MANUSCRIPT_FILES):
    failures = []
    for manuscript in paths:
        path = _repo_path(manuscript)
        if not path.is_file():
            failures.append(f"manuscript does not exist: {manuscript}")
            continue
        text = path.read_text(encoding="utf-8")
        for forbidden in OVERSTRONG_TEXT:
            if forbidden in text:
                failures.append(f"{manuscript}: overstrong claim remains: {forbidden}")
    return failures


def validate_claims(claims, scan_manuscripts=True):
    failures = []
    seen = set()
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            failures.append(f"claim[{index}] must be an object")
            continue
        missing = sorted(REQUIRED - claim.keys())
        if missing:
            failures.append(f"claim[{index}] missing fields: {', '.join(missing)}")
            continue
        claim_id = claim["claim_id"]
        if not isinstance(claim_id, str) or not claim_id.strip():
            failures.append(f"claim[{index}] has an empty claim_id")
        elif claim_id in seen:
            failures.append(f"duplicate claim_id: {claim_id}")
        seen.add(claim_id)
        if claim["status"] not in STATUSES:
            failures.append(f"{claim_id}: invalid status {claim['status']!r}")
        if not isinstance(claim["manuscript_files"], list) or not claim["manuscript_files"]:
            failures.append(f"{claim_id}: manuscript_files must be a nonempty array")
        else:
            for manuscript in claim["manuscript_files"]:
                if not _valid_repo_relative(manuscript):
                    failures.append(f"{claim_id}: manuscript must be repository-relative")
        if claim["source"] and not _valid_repo_relative(claim["source"]):
            failures.append(f"{claim_id}: source must be repository-relative")
        if claim["status"] == "verified":
            source = _repo_path(claim["source"]) if _valid_repo_relative(claim["source"]) else None
            if source is None or not source.is_file():
                failures.append(f"{claim_id}: verified source does not exist")
            if not isinstance(claim["command"], str) or not claim["command"].strip():
                failures.append(f"{claim_id}: verified claim requires a command")
            elif claim["command"].strip().lower() in {"false", "true", ":", "noop", "echo"}:
                failures.append(f"{claim_id}: verified command is a noop")
            digest = claim.get("source_sha256")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                failures.append(f"{claim_id}: verified claim requires source SHA-256")
            elif source is not None and source.is_file():
                actual = hashlib.sha256(source.read_bytes()).hexdigest()
                if actual != digest:
                    failures.append(f"{claim_id}: source SHA-256 mismatch")
            assertions = claim.get("assertions")
            if not isinstance(assertions, list) or not assertions:
                failures.append(f"{claim_id}: verified claim requires assertions")
            else:
                asserted_files = set()
                purposes = set()
                for assertion_index, assertion in enumerate(assertions):
                    prefix = f"{claim_id}: assertion[{assertion_index}]"
                    if not isinstance(assertion, dict):
                        failures.append(f"{prefix} must be an object")
                        continue
                    filename = assertion.get("file")
                    if not _valid_repo_relative(filename):
                        failures.append(f"{prefix} file must be repository-relative")
                        continue
                    asserted_files.add(filename)
                    purpose = assertion.get("purpose")
                    if purpose not in {"value", "scope"}:
                        failures.append(f"{prefix} purpose must be value or scope")
                    else:
                        purposes.add(purpose)
                    matchers = [key for key in ("literal", "regex") if key in assertion]
                    if len(matchers) != 1 or not isinstance(assertion.get(matchers[0], ""), str):
                        failures.append(f"{prefix} requires exactly one literal or regex")
                        continue
                    assertion_path = _repo_path(filename)
                    if not assertion_path.is_file():
                        failures.append(f"{prefix} file does not exist")
                        continue
                    content = assertion_path.read_text(encoding="utf-8")
                    if matchers[0] == "literal":
                        matched = assertion["literal"] in content
                    else:
                        try:
                            matched = re.search(assertion["regex"], content, re.MULTILINE) is not None
                        except re.error as error:
                            failures.append(f"{prefix} invalid regex: {error}")
                            continue
                    if not matched:
                        failures.append(f"{prefix} does not match file content")
                required_files = {claim["source"], *claim["manuscript_files"]}
                missing_assertions = required_files - asserted_files
                if missing_assertions:
                    failures.append(
                        f"{claim_id}: assertions do not cover source/manuscript files: "
                        + ", ".join(sorted(missing_assertions))
                    )
                if purposes != {"value", "scope"}:
                    failures.append(f"{claim_id}: assertions must cover claim value and scope")
            if claim_id.startswith("mc-") and not _repo_path(claim["source"]).name.endswith(
                ("summary.json", ".jsonl.gz")
            ):
                failures.append(f"{claim_id}: verified Monte Carlo claim requires frozen results")
            if claim_id.startswith("mc-"):
                for digest_field in ("manifest_sha256", "raw_sha256", "gzip_sha256"):
                    digest_value = claim.get(digest_field)
                    if not isinstance(digest_value, str) or not re.fullmatch(
                        r"[0-9a-f]{64}", digest_value
                    ):
                        failures.append(
                            f"{claim_id}: verified Monte Carlo claim requires {digest_field}"
                        )
        if scan_manuscripts and isinstance(claim["manuscript_files"], list):
            for manuscript in claim["manuscript_files"]:
                path = _repo_path(manuscript)
                if not path.is_file():
                    failures.append(f"{claim_id}: manuscript does not exist: {manuscript}")
                    continue
                text = path.read_text(encoding="utf-8")
                for forbidden in SUPERSEDED_TEXT:
                    if forbidden in text:
                        failures.append(f"{manuscript}: superseded value remains: {forbidden}")
    return failures


def main():
    failures = validate_claims(load_claims()) + scan_manuscript_language()
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        return 1
    print("Claim ledger validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
