# Protocol-v2 Workflow Checkpoint Guard Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task.

**Goal:** Prevent protocol-v2 workers from taking unapproved stage jumps or replaying a previously successful external stage after a lease-recovery restart.

**Architecture:** Keep execution deployment-owned and fail-closed.  The durable worker owns a small, server-defined transition contract; it validates every executor outcome against that contract and persists the next safe cursor atomically with the successful stage receipt.  A newly leased task inspects its durable receipt before invoking an executor, so a crash after a successful receipt advances or finalizes without repeating the side effect.

**Tech Stack:** Python 3.11, FastAPI services, SQLAlchemy async ORM, pytest.

---

### Task 1: Capture the recovery regression

**Files:**

- Modify: `src/backend/tests/test_ai_research_workflow_worker.py`
- Test: `src/backend/tests/test_ai_research_workflow_worker.py`

**Step 1: Write failing tests**

Add one test that leaves a successful `CLARIFY` stage receipt behind an expired lease, then runs a replacement worker.  It must execute only `GENERATE`, never repeat `CLARIFY`.  Add one test whose `CLARIFY` executor asks to jump to an unapproved stage and expects a terminal `RESEARCH_STAGE_TRANSITION_INVALID` result.

**Step 2: Run the focused tests to verify RED**

Run:

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest -q \
  tests/test_ai_research_workflow_worker.py
```

Expected: the new recovery test re-invokes `CLARIFY`, and the invalid-transition test is not rejected by the worker.

### Task 2: Persist and validate the safe transition

**Files:**

- Modify: `src/backend/app/services/research/workflow_worker.py`
- Modify: `src/backend/app/services/research/stage_attempt.py`
- Test: `src/backend/tests/test_ai_research_workflow_worker.py`

**Step 1: Implement the minimum graph contract**

Define the server-owned v2 core graph `CLARIFY -> GENERATE -> terminal`.  Reject any successful executor `next_stage` other than the configured successor.  Preserve the existing deployment-owned executor injection and existing missing-executor fail-closed behavior.

**Step 2: Make checkpoint advancement atomic**

Extend the stage-attempt completion boundary to persist the next cursor on the task and run in the same transaction as a successful receipt.  Before executing a newly claimed cursor, detect the latest successful receipt for that cursor: continue at its defined successor, or finalize if it is the terminal stage.

**Step 3: Run focused tests to verify GREEN**

Run the Task 1 command.  Expected: all workflow-worker tests pass and the recording executor reports no duplicate `CLARIFY` call.

### Task 3: Regression and evidence update

**Files:**

- Modify: `docs/iterations/迭代196-改进优化ai生成策略流程/IMPLEMENTATION_STATUS.md` in the main checkout after verification
- Modify: `docs/iterations/迭代196-改进优化ai生成策略流程/ACCEPTANCE_REPORT_20260905.md` in the main checkout after verification

**Step 1: Static validation**

Run:

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base ruff check \
  app/services/research/workflow_worker.py \
  app/services/research/stage_attempt.py \
  tests/test_ai_research_workflow_worker.py
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base ruff format --check \
  app/services/research/workflow_worker.py \
  app/services/research/stage_attempt.py \
  tests/test_ai_research_workflow_worker.py
```

**Step 2: Scope regression**

Run:

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest -q \
  tests/test_ai_research_task_runner.py \
  tests/test_ai_research_stage_attempt.py \
  tests/test_ai_research_workflow_worker.py
```

**Step 3: Update evidence accurately**

Record the exact test output and explain that the guard improves T1 checkpoint safety but does not replace a real Provider, isolated runner, MySQL, T2 data, or T3 staging evidence.  Verify documentation links with:

```bash
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/ci/check_doc_links.py
```

No commit, push, deployment, runtime restart, Docker startup, provider call, or production database action is authorized by this plan.
