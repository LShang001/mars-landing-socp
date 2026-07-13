# Stage B1 Free-Time Mesh Study Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and freeze an independently audited, dry-mass-feasible fixed-time SOCP study with deterministic terminal-time search and per-mesh ECOS/Clarabel convergence evidence, without changing the original handwritten matrix implementation.

**Architecture:** A new immutable physical-model configuration feeds a fixed-`(N, tf)` CVXPY SOCP and a parameterized auditor. A separate deterministic search layer owns candidate generation and failure taxonomy; JSONL remains authoritative and aggregation/figures/paper consume only validated frozen evidence. `legacy_tf81_v1` remains a separate, protected reference asset.

**Tech Stack:** Python 3, NumPy, CVXPY, ECOS, Clarabel, unittest, JSON/JSONL, Matplotlib, XeLaTeX.

---

### Task 1: Freeze the Stage B1 manifest contract

**Files:**
- Create: `experiments/studies/free_time_mesh_v1.json`
- Create: `experiments/study_contracts.py`
- Create: `tests/test_study_contracts.py`

- [ ] **Step 1: Write failing tests** for exact fields, `model_id=physical_free_tf_v1`, strictly increasing meshes, decimal search levels, solver set, positive audit/cross-solver/convergence tolerances, and rejection of unknown fields or legacy model identity.
- [ ] **Step 2: Run** `python3 -m unittest -v tests/test_study_contracts.py`; expect failures because `study_contracts` does not exist.
- [ ] **Step 3: Implement** a strict validator and a manifest with meshes `[20, 30, 40, 60]`, bounded coarse-to-fine time levels, ECOS search plus Clarabel confirmation, and explicit provenance fields.
- [ ] **Step 4: Run** the focused tests and `git diff --check`; expect all pass.
- [ ] **Step 5: Commit and push** `feat: 定义自由时间网格研究契约`.

### Task 2: Add the immutable physically corrected fixed-time SOCP

**Files:**
- Create: `experiments/physical_model.py`
- Create: `tests/test_physical_model.py`

- [ ] **Step 1: Write failing tests** proving configuration validation, `N+1` state versus `N` control shapes, explicit dry-mass constraints, objective scaling by `dt`, no mutation of `MarsLanding.mars_params`, and distinct model/legacy labels.
- [ ] **Step 2: Run** `python3 -m unittest -v tests/test_physical_model.py`; expect import/behavior failures.
- [ ] **Step 3: Implement** a frozen `PhysicalModelConfig`, fixed-time CVXPY builder, ECOS/Clarabel adapters, structured solve result, and exact status mapping. Never import generated CCS into the handwritten target.
- [ ] **Step 4: Run** focused tests plus `python3 -m unittest -v tests/test_handwritten_asset.py`; expect all pass and the handwritten asset digest/source checks unchanged.
- [ ] **Step 5: Commit and push** `feat: 新增干重约束固定时间SOCP模型`.

### Task 3: Implement parameterized node and interval auditing

**Files:**
- Modify: `experiments/physical_model.py`
- Modify: `tests/test_physical_model.py`

- [ ] **Step 1: Write failing tests** with synthetic exact trajectories and injected dynamics, cone, mass, envelope, objective-consistency, and midpoint violations; assert metric names and finite scalar outputs.
- [ ] **Step 2: Run** the focused audit tests; expect missing metrics/failures.
- [ ] **Step 3: Implement** auditing from each result's own `N/tf/config`, including dense interval samples and a classification function that separates inaccurate, infeasible, physical violation, and errors.
- [ ] **Step 4: Run** focused tests and legacy `tests/test_solution_audit.py`; expect both new and old auditors to pass without changing legacy semantics.
- [ ] **Step 5: Commit and push** `feat: 审计自由时间轨迹节点与区间约束`.

### Task 4: Add deterministic terminal-time search

**Files:**
- Create: `experiments/free_time_search.py`
- Create: `tests/test_free_time_search.py`

- [ ] **Step 1: Write failing tests** using a fake solver for decimal-stable candidate IDs, sorted de-duplication, refinement around the best audited point, independent search per N, preservation of all failures, and no conversion of exceptions into infeasibility.
- [ ] **Step 2: Run** `python3 -m unittest -v tests/test_free_time_search.py`; expect import failures.
- [ ] **Step 3: Implement** pure candidate generation/search functions and structured records; keep solving injectable so orchestration tests require no numerical solver.
- [ ] **Step 4: Run** focused tests; expect deterministic identical records across repeated runs.
- [ ] **Step 5: Commit and push** `feat: 实现确定性终端时间分层搜索`.

### Task 5: Record raw runs and recompute summaries

**Files:**
- Create: `experiments/run_free_time_mesh.py`
- Create: `experiments/aggregate_free_time_mesh.py`
- Create: `tests/test_free_time_evidence.py`

- [ ] **Step 1: Write failing tests** for append-only JSONL records, exact schema, duplicate sample rejection, all-attempt denominator, per-N optimum, ECOS/Clarabel agreement, unresolved boundary flags, and summary determinism.
- [ ] **Step 2: Run** `python3 -m unittest -v tests/test_free_time_evidence.py`; expect import failures.
- [ ] **Step 3: Implement** runner and streaming aggregator with atomic summary writes, manifest digest binding, bounded line sizes, and explicit error records.
- [ ] **Step 4: Run** focused tests and a tiny smoke manifest; validate record count and independently recomputed summary.
- [ ] **Step 5: Commit and push** `feat: 冻结自由时间逐点证据与汇总`.

### Task 6: Execute and confirm the registered mesh study

**Files:**
- Create: `experiments/results/free_time_mesh_v1.jsonl`
- Create: `experiments/results/free_time_mesh_v1.jsonl.gz`
- Create: `experiments/results/free_time_mesh_v1.summary.json`
- Create: `docs/evidence/stage-b1-audit.md`

- [ ] **Step 1: Run** the registered ECOS study and preserve every attempt, including solver failures.
- [ ] **Step 2: Run** Clarabel confirmation at every mesh optimum, neighbors, and representative boundaries.
- [ ] **Step 3: Aggregate and independently audit** digests, counts, per-mesh optima, dense defects, cross-solver deltas, and convergence thresholds.
- [ ] **Step 4: Review anomalies** without deleting or relabeling failures; amend the model/search only through a new TDD cycle and rerun affected evidence.
- [ ] **Step 5: Commit and push** `research: 冻结物理修正自由时间网格证据`.

### Task 7: Bind figures, paper claims, and agent workflow

**Files:**
- Modify: `paper/figures/generate_all.py`
- Create: `paper/data/free_time_mesh_v1.summary.json`
- Modify: `paper/evidence/claims.json`
- Modify: `paper/chapters/ch2_formulation.tex`
- Modify: `paper/chapters/ch5_results.tex`
- Modify: `paper/chapters/ch7_conclusion.tex`
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `ci/validate.sh`
- Create/modify: corresponding tests under `tests/`

- [ ] **Step 1: Write failing tests** requiring claim-to-digest binding, figure inputs from frozen summary, explicit legacy/new-model wording, and Stage B1 confirmation checks in CI.
- [ ] **Step 2: Run** focused tests; expect missing claim/figure/workflow failures.
- [ ] **Step 3: Implement** evidence-driven plots and conservative manuscript text. State that `MarsLanding.c` is original independent handwritten work and that the new model does not replace it.
- [ ] **Step 4: Regenerate all PDF/PNG figures and compile XeLaTeX twice. Render every paper page plus each figure preview; inspect clipping, labels, sizes, whitespace, captions, and dense Chapter 5 pages.
- [ ] **Step 5: Commit and push** the figures, source, claim ledger, workflow documentation, and `paper/mars_landing_socp.pdf` with `paper: 加入自由时间网格收敛证据`.

### Task 8: Independent reviews and full verification

**Files:**
- Modify only files required to resolve confirmed review findings.

- [ ] **Step 1: Dispatch spec compliance review** against the Stage B1 design and this plan; fix every confirmed missing/extra behavior with TDD.
- [ ] **Step 2: Dispatch code/data quality review** covering numerical semantics, status taxonomy, evidence immutability, security/resource bounds, and handwritten-asset isolation; fix all critical/important findings and re-review.
- [ ] **Step 3: Run fresh verification:** complete unittest suite, model/handwritten/literature checks, `bash ci/validate.sh --quick`, Stage B1 confirmation, C/Python golden regression, figure generation, two-pass XeLaTeX, and PDF page/image audit.
- [ ] **Step 4: Check** `git diff --check`, tracked/untracked scope, evidence digests, and `git status`; do not stage existing build artifacts.
- [ ] **Step 5: Commit and push** final review fixes and Stage B1 audit. Keep the long-term top-tier goal active because B2-B4 and submission freeze remain.

