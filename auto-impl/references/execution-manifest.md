# Execution manifest

Use JSON so the scheduler needs no third-party dependency. Store mutable runtime state under `<repo>/.codex/auto-impl/` and never commit it.

## Schema

```json
{
  "schema_version": 1,
  "batch_id": "user-management",
  "target_branch": "dev",
  "policy": {
    "max_repair_attempts": 2,
    "integrate_on": ["PASS"],
    "push_mode": "batch-end"
  },
  "tickets": {
    "T1": {
      "ticket_path": "docs/tickets/20260807/T1.md",
      "plan_path": "docs/plans/20260807/T1_plan.md",
      "route": "api",
      "branch": "feature/t1",
      "depends_on": [],
      "conflicts_with": [],
      "resources": ["src/main/java/example/UserService.java", "table:users"],
      "priority": 0,
      "state": "PENDING",
      "attempts": 0,
      "base_ref": null,
      "verdict": null,
      "commits": {},
      "last_error": null,
      "history": []
    }
  }
}
```

## Fields

- `depends_on`: predecessors that must reach `INTEGRATED` or `DONE` before this ticket can run.
- `conflicts_with`: ticket IDs that must not implement concurrently, even without a functional dependency.
- `resources`: normalized file paths or namespaced resources such as `table:users`, `endpoint:/api/users`, and `port:8080`.
- `priority`: larger values run first. For equal priority the scheduler favors the longer remaining dependency chain, then ticket ID.
- `attempts`: implementation attempts, including the first attempt. `max_repair_attempts` counts additional repair attempts.
- `commits`: state-keyed evidence, such as `implemented`, `verified`, and `integrated`.
- `history`: scheduler-owned transition records in UTC.

## States

```text
PENDING -> RUNNING -> IMPLEMENTED -> VERIFYING -> VERIFIED -> INTEGRATING -> INTEGRATED -> DONE
                 \-> REPAIR -------> RUNNING
                 \-> FAILED
VERIFYING -------> REPAIR | BLOCKED | FAILED
INTEGRATING -----> REPAIR | FAILED
BLOCKED/FAILED --> REPAIR only after a concrete recovery action
```

`ready` returns `PENDING` tickets whose dependencies are integrated and `REPAIR` tickets whose retry budget remains. It excludes resource conflicts with active tickets and among the returned tickets.

## Dependency rules

Add a dependency when a ticket needs another ticket's behavior or code to exist before implementation. Use `conflicts_with` or shared `resources` when tickets are logically independent but unsafe to implement concurrently. Do not add dependencies merely to fit the agent slot limit; the scheduler handles capacity.

Prefer IDs derived from ticket filenames and keep them stable across resume. Use repository-relative paths in the manifest and absolute paths only when invoking agents.
