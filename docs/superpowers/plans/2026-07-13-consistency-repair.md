# Consistency Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect model metadata drift automatically and align repository documentation with the retained handwritten C SOCP implementation.

**Architecture:** A dependency-free Python checker will parse only stable C `#define` and scalar assignment forms, compare them with the Python model constants and generated header dimensions, and exit nonzero on drift. The handwritten `MarsLanding.c` remains an independently maintained original CRS-to-CCS implementation; documentation will describe the distinction explicitly.

**Tech Stack:** Python 3 standard library, Bash CI, CMake, ECOS C executables, Markdown, LaTex.

---

### Task 1: Add a failing handwritten-model metadata check

**Files:**
- Create: `MarsLanding/check_model_consistency.py`
- Modify: `ci/validate.sh`
- Test: `MarsLanding/check_model_consistency.py`

- [ ] **Step 1: Write the failing checker assertions**

Implement a Python script that reads `MarsLanding.h`, `MarsLanding.c`, and `MarsLandingAutoData.h`; it must require `P_EQ=223`, `M_G=341`, `NNZA=733`, `NNZG=403`, and verify that hand-coded `g`, `m_0`, `T_max`, `T_min`, `T_2`, `n_T`, `phi`, `theta_alt`, and `t_f` match `mars_params.py`.

- [ ] **Step 2: Run the checker to verify it fails**

Run: `python3 MarsLanding/check_model_consistency.py`

Expected: fail because no checker exists.

- [ ] **Step 3: Implement the minimal checker and CI hook**

Use `pathlib`, `re`, `math`, and `importlib` from the standard library. Print one failure per mismatch and a concise success summary. Insert the checker before the solver invocations in `ci/validate.sh`.

- [ ] **Step 4: Run the checker to verify it passes**

Run: `python3 MarsLanding/check_model_consistency.py`

Expected: exit 0 and report the handwritten and automatic models agree on required metadata.

### Task 2: Correct repository documentation

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Correct source-of-truth and dimension claims**

State that `mars_params.py` is the source for Python and generated-data paths, while the handwritten C implementation is maintained independently and checked for consistency. Change the README equality dimension to 223 and use downward gravity in the displayed dynamics.

- [ ] **Step 2: Correct stale generator ordering guidance**

Replace the stale claim that `mars_codegen.py` interleaves rows by step with the implemented order: all 124 linear rows, 93 glide-slope SOC rows, then 124 thrust SOC rows.

- [ ] **Step 3: Verify documentation claims**

Run: `rg -n "7 \+ 7×N = 217|按 k 交错|唯一来源" README.md AGENTS.md MarsLanding`

Expected: no stale claim remains; the C/Python parameter boundary is explicit.

### Task 3: Correct paper claims tied to implementation facts

**Files:**
- Modify: `paper/chapters/ch1_intro.tex`

- [ ] **Step 1: Correct matrix dimensions**

Replace the obsolete summary dimensions with `A` as 223 by 341 and `G` as 341 by 341.

- [ ] **Step 2: Correct benchmark provenance and unit**

Remove the unsupported ARM Cortex-A72 and 8 microsecond claims. Describe the current repository benchmark as approximately 8 milliseconds per solve on the configured host, keeping no unverified hardware extrapolation.

- [ ] **Step 3: Verify no stale claims remain**

Run: `rg -n "8 \$\\mu|8 μs|Cortex-A72|31 行、341 列、733|279 行、341" paper/chapters`

Expected: no matches.

### Task 4: Validate the repair end to end

**Files:**
- Verify: `MarsLanding/check_model_consistency.py`
- Verify: `ci/validate.sh`
- Verify: `build/bin/ecos_avx`, `build/bin/ecos_scalar`, `build/bin/ecos_auto`

- [ ] **Step 1: Build all targets**

Run: `cmake --build build -j4`

Expected: exit 0.

- [ ] **Step 2: Run metadata and solver validation**

Run: `bash ci/validate.sh`

Expected: checker passes and all installed solver paths report approximately 400.7 kg.

- [ ] **Step 3: Inspect the final patch**

Run: `git diff --check && git diff --stat && git status --short`

Expected: no whitespace errors and no user-owned untracked output is modified.
