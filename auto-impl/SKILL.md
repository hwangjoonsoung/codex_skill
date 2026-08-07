---
name: auto-impl
description: Automate a BOMS feature from one requirement, a feature-list Markdown file, or an existing ticket directory through ticket creation, plan generation, cross-ticket dependency analysis, dependency-aware parallel and sequential implementation, automated verification, repair retries, and serial integration into local dev for one final human review. Use when the user wants minimal-intervention implementation of multiple related Java project requirements without manually reviewing every ticket or repeatedly invoking plan-impl. Do not use board-* skills.
---

# Auto Implement

## Purpose

Run one resumable, dependency-aware implementation batch from requirements to a final human review on local `dev`. Reuse `ticket-create`, `plan-impl --no-chain`, the existing implementation agents, `verify-impl`, and the `integrator` agent. Keep `board-*`, `finalize-impl`, and `commit-impl` outside this pipeline.

Treat explicit invocation of this skill as authorization to create tickets, plans, feature branches, commits, verification evidence, and local `dev` integrations within the selected repository. Never push unless the user includes `--push`.

## Invocation

```text
$auto-impl <requirement text | feature-list.md | ticket directory>
$auto-impl <input> [--push] [--max-repair <N>]
$auto-impl --resume <execution-manifest.json> [--push]
```

Defaults:

- Integration target: local `dev`
- Human gate: once after the batch reaches final review, plus a single consolidated question only when a true blocking ambiguity exists
- Push: disabled
- Repair retries: `2`
- Automatic integration verdict: `PASS` only

## Invariants

1. Read the target repository's `AGENTS.md` files before changing it and follow their most specific applicable instructions.
2. If Maven manages dependencies, do not attempt a Maven build or test. Record the skipped evidence; do not silently convert an incomplete verification into `PASS`.
3. Preserve unrelated user changes. Never use `git add .`, `git add -A`, force checkout, force push, destructive reset, or broad cleanup.
4. Let implementation agents change code only in their allowed ownership areas. The main session owns orchestration, the execution manifest, worktree lifecycle, and branch integration.
5. Run implementation concurrently only for scheduler-ready tickets. Run verification one ticket at a time when it shares an app, port, browser, or database. Run integration strictly one ticket at a time.
6. Do not let parallel agents write directly to `dev` or to the same worktree.
7. Integrate only a verified verdict permitted by the manifest policy. Default to `PASS`; block `FAIL` and `INCONCLUSIVE`.
8. Keep every feature branch until final review finishes. Do not delete failed worktrees automatically.

## Phase 0: Preflight

1. Resolve the target Git repository from the input path or current directory. Stop if it is not a Git repository.
2. Locate and read applicable `AGENTS.md` files.
3. Confirm that local `dev` exists. Record `dev` HEAD, current branch, worktrees, and `git status --short`.
4. If unrelated dirty changes prevent safe branch switching or integration, stop with the exact paths. Do not stash them automatically.
5. When `origin/dev` exists, fetch it and compare it with local `dev`. Fast-forward a behind local `dev`; allow an intentionally ahead local `dev`; stop on divergence. Never reset local work.
6. Check out local `dev` before ticket creation and planning. Stop rather than switching over unresolved dirty changes.
7. Parse `--push` and `--max-repair`. Reject a negative retry value.
8. Resolve this skill directory and the scheduler script path. Use absolute paths when invoking the script.

## Phase 1: Produce tickets

If the input is an existing ticket file or directory, collect only its direct ticket Markdown files and skip ticket creation.

Otherwise follow `ticket-create/SKILL.md`:

- For a feature-list path, use its bulk protocol.
- For free text containing several independently testable requirements, split it into numbered requirement items and run the bulk ticket-writer protocol without forcing the user to approve each split.
- For one requirement, use the single-ticket protocol.
- Never let `ticket_writer` choose implementation route or dependency order.

After creation, scan every ticket's Confirmation section. Classify unresolved items:

- Resolve a reversible technical choice only when an applicable project rule or an explicit batch policy supplies the default. Record the rule or policy as the decision source.
- Treat missing business behavior, destructive data changes, authorization/security semantics, and externally visible contract choices as blocking.
- Present all blocking items in one consolidated question. Do not ask one question per ticket.
- If no blocking item exists, continue without requiring the user to read the tickets.

## Phase 2: Produce plans without implementation

Invoke `plan-impl <ticket directory> --no-chain`. Reuse existing plans and collect each successful ticket's:

- ticket path
- plan path
- route: `api`, `front`, or `fullstack`
- feature branch name
- planned files, tables, APIs, and other shared resources

Exclude planning failures from execution and record their exact reason. Do not invoke the normal `plan-impl` implementation chain because it does not schedule cross-ticket dependencies.

## Phase 3: Build the execution manifest

Read [references/execution-manifest.md](references/execution-manifest.md) before creating or editing a manifest.

Read all selected tickets and plans as one batch. Derive:

- `depends_on`: required implementation predecessors
- `resources`: files, tables, endpoints, configuration, ports, or other exclusive resources
- `conflicts_with`: explicit ordering constraints not represented by a business dependency
- `priority`: business priority when stated; otherwise `0`

Never use a standalone `parallel: true|false` flag. A ticket is parallel-ready only when all dependencies are integrated and it has no resource conflict with active work.

Store runtime state at:

```text
<repo>/.codex/auto-impl/<batch-id>.json
```

Do not stage or commit this runtime file. Create its parent directory if missing. Validate it before implementation:

```text
python <skill-dir>/scripts/dag_scheduler.py validate <manifest>
```

Stop before implementation on unknown dependencies, duplicate ticket IDs, invalid states, or dependency cycles.

## Phase 4: Schedule implementation

Repeat until no runnable or active ticket remains.

1. Ask the scheduler for the next ready set, limiting it to the currently available worker slots:

   ```text
   python <skill-dir>/scripts/dag_scheduler.py ready <manifest> --limit <available-worker-slots>
   ```

2. Before spawning a worker, transition the ticket to `RUNNING` and record the current local `dev` SHA as `base_ref`:

   ```text
   python <skill-dir>/scripts/dag_scheduler.py transition <manifest> <ticket-id> RUNNING --base-ref <sha> --branch <branch>
   ```

3. Spawn ready tickets concurrently up to the available slots, with one isolated worktree per ticket. State explicit file ownership and tell every worker that other agents are active and must not revert their changes.
4. Use the plan route:
   - `api`: spawn `backend_engineer`.
   - `front`: spawn `frontend_engineer`.
   - `fullstack`: use one shared ticket worktree; run `backend_engineer`, wait for success, then run `frontend_engineer` on the same branch. Different fullstack tickets may run concurrently when the scheduler declares them ready and resources do not conflict.
5. Require structured results containing result, branch, commit SHAs, validation status, and notes.
6. On success, transition `RUNNING -> IMPLEMENTED`. On failure, transition to `REPAIR` when retries remain; otherwise transition to `FAILED`.
7. Remove a successful implementation worktree before non-isolated verification so the feature branch can be checked out. Keep failed worktrees for inspection.

Treat each selected ready set as one implementation wave. Keep local `dev` fixed at the recorded `base_ref` until every worker in that wave has finished and its feature branch is proven to descend from that SHA. Do not verify, integrate, or otherwise advance `dev` while a wave still has an active implementation worker. This preserves the existing engineer contract that creates branches from local `dev`.

After the wave finishes, verify and integrate its successful tickets serially. A later ticket in the same wave may have started from the older wave base; the integrator must merge the latest local `dev` into that feature branch before fast-forwarding `dev`.

## Phase 5: Verify and repair

Verify implemented tickets one at a time:

1. Transition `IMPLEMENTED -> VERIFYING`.
2. Invoke `verify-impl <ticket path>` and parse its `PASS`, `FAIL`, or `INCONCLUSIVE` verdict and report path.
3. On `PASS`, transition to `VERIFIED` and record the verification commit.
4. On `FAIL`, transition to `REPAIR` when repair retries remain. Recreate an isolated worktree on the existing feature branch and send the applicable implementation agent the ticket, plan, verification report, existing branch, and `mode: repair`. Require a new repair commit, then verify again.
5. On `INCONCLUSIVE`, retry only a clearly transient verification failure once. Otherwise transition to `BLOCKED`; never integrate it under the default policy.
6. If the existing implementation agent cannot resume an existing branch, mark the ticket `BLOCKED` with `REPAIR_UNSUPPORTED` instead of creating an unrelated replacement branch.
7. After each verifier run, require a clean feature branch and check out local `dev` so the feature branch is free for a repair or integrator worktree. If unexpected dirty files remain, stop that ticket and report the exact paths.

Continue unrelated ready tickets while descendants of `FAILED` or `BLOCKED` tickets remain unavailable.

## Phase 6: Integrate verified tickets into local dev

Process the integration queue serially.

1. Transition `VERIFIED -> INTEGRATING`.
2. Confirm that the main workspace is clean and has local `dev` checked out.
3. Ensure the feature branch contains the current local `dev` by spawning `integrator` in an isolated worktree with:

   ```json
   {
     "ticket_path": "<absolute-ticket-path>",
     "plan_path": "<absolute-plan-path>",
     "branch": "<feature-branch>",
     "base_ref": "dev"
   }
   ```

4. Let `integrator` resolve only unambiguous conflicts and run validations allowed by `AGENTS.md`. Stop that ticket on an ambiguous conflict or invalid result.
5. After integrator success, confirm that current `dev` is an ancestor of the feature branch.
6. Advance local `dev` only with `git merge --ff-only <feature-branch>`. Never create a merge commit on `dev`, and never force it.
7. Record the new `dev` SHA and transition `INTEGRATING -> INTEGRATED`.
8. Let the scheduler unlock descendants only after this transition.

If integration fails, leave local `dev` at its previous SHA and move the ticket to `REPAIR` or `FAILED`. Continue unrelated tickets.

## Phase 7: Finish or pause

Run the scheduler summary:

```text
python <skill-dir>/scripts/dag_scheduler.py summary <manifest>
```

- If ready work remains, continue Phase 4.
- If only failed or blocked ancestors remain, report them once with their blocked descendants and stop for user input.
- When every ticket is `INTEGRATED`, optionally run an aggregate verification allowed by project rules.
- If `--push` was supplied, fetch `origin/dev`, require local `dev` to contain it without divergence, and push local `dev` once at batch end. Never force-push.
- Present one final review containing the local dev SHA, push status, ticket results, assumptions, skipped Maven evidence, and verification report paths.

Wait for one human decision:

- Approval: transition all `INTEGRATED` tickets to `DONE` and finish.
- Revision feedback: create only the necessary revision tickets, plan them, append them to the same manifest with dependencies on the affected integrated tickets, validate the graph, and resume Phase 4. Prefer fix-forward; do not revert existing work unless explicitly requested.

## Resume

For `--resume`:

1. Validate the manifest.
2. Compare recorded branch and commit SHAs with actual Git refs.
3. Reconcile only facts that can be proven from commits and verification reports.
4. Do not infer that an interrupted `RUNNING`, `VERIFYING`, or `INTEGRATING` action succeeded. Inspect its branch/worktree and either complete the state transition from evidence or mark it `BLOCKED` with the reason.
5. Continue from the scheduler's ready set.

## Existing skill boundaries

- Use `ticket-create` for ticket-writing rules.
- Use `plan-impl --no-chain` only for ticket plans and routes.
- Do not call `impl-api` or `impl-front` wrappers from this pipeline; spawn their underlying engineer roles directly so the scheduler controls readiness and worktrees.
- Use `verify-impl` for ticket verification, but treat its verdict as input to this pipeline instead of a terminal report.
- Do not call `merge-impl` per ticket. Its contract requires prior human approval and targets final standalone integration.
- Leave `finalize-impl` and `commit-impl` optional and outside the automatic pipeline.

## Deterministic scheduler

Use `scripts/dag_scheduler.py` for validation, ready selection, state transitions, and summaries. Do not manually bypass a rejected transition. The script prioritizes explicit priority and longer dependency chains, prevents cyclic graphs, and excludes conflicting resources from the same ready set.
