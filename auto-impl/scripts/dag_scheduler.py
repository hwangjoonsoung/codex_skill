#!/usr/bin/env python3
"""Validate and advance an auto-impl execution manifest."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VALID_STATES = {
    "PENDING",
    "RUNNING",
    "IMPLEMENTED",
    "VERIFYING",
    "VERIFIED",
    "INTEGRATING",
    "INTEGRATED",
    "REPAIR",
    "BLOCKED",
    "FAILED",
    "DONE",
}

ACTIVE_STATES = {"RUNNING", "VERIFYING", "INTEGRATING"}
DEPENDENCY_COMPLETE_STATES = {"INTEGRATED", "DONE"}

TRANSITIONS = {
    "PENDING": {"RUNNING", "BLOCKED", "FAILED"},
    "RUNNING": {"IMPLEMENTED", "REPAIR", "FAILED", "BLOCKED"},
    "IMPLEMENTED": {"VERIFYING", "REPAIR", "FAILED", "BLOCKED"},
    "VERIFYING": {"VERIFIED", "REPAIR", "BLOCKED", "FAILED"},
    "VERIFIED": {"INTEGRATING", "REPAIR", "BLOCKED", "FAILED"},
    "INTEGRATING": {"INTEGRATED", "REPAIR", "FAILED", "BLOCKED"},
    "INTEGRATED": {"DONE", "REPAIR"},
    "REPAIR": {"RUNNING", "FAILED", "BLOCKED"},
    "BLOCKED": {"REPAIR", "FAILED"},
    "FAILED": {"REPAIR"},
    "DONE": set(),
}


class ManifestError(ValueError):
    pass


def load_manifest(path: Path) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ManifestError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle, object_pairs_hook=reject_duplicate_keys)
    except FileNotFoundError as exc:
        raise ManifestError(f"manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ManifestError("manifest root must be an object")
    return data


def save_manifest(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _require_list(entry: dict[str, Any], field: str, ticket_id: str) -> list[Any]:
    value = entry.get(field, [])
    if not isinstance(value, list):
        raise ManifestError(f"{ticket_id}.{field} must be an array")
    return value


def validate_manifest(data: dict[str, Any]) -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not isinstance(data.get("batch_id"), str) or not data.get("batch_id", "").strip():
        errors.append("batch_id must be a non-empty string")
    if data.get("target_branch") != "dev":
        errors.append("target_branch must be 'dev' for auto-impl v1")

    policy = data.get("policy")
    if not isinstance(policy, dict):
        errors.append("policy must be an object")
        policy = {}
    max_repairs = policy.get("max_repair_attempts", 2)
    if not isinstance(max_repairs, int) or isinstance(max_repairs, bool) or max_repairs < 0:
        errors.append("policy.max_repair_attempts must be a non-negative integer")
    integrate_on = policy.get("integrate_on", ["PASS"])
    if integrate_on != ["PASS"]:
        errors.append("policy.integrate_on must be exactly ['PASS'] for auto-impl v1")

    tickets = data.get("tickets")
    if not isinstance(tickets, dict) or not tickets:
        errors.append("tickets must be a non-empty object")
        return {"errors": errors, "warnings": warnings}

    ids = set(tickets)
    dependencies: dict[str, list[str]] = {}
    conflicts: dict[str, list[str]] = {}

    for ticket_id, entry in tickets.items():
        if not isinstance(ticket_id, str) or not ticket_id.strip():
            errors.append("ticket IDs must be non-empty strings")
            continue
        if not isinstance(entry, dict):
            errors.append(f"{ticket_id} must be an object")
            continue

        route = entry.get("route")
        if route not in {"api", "front", "fullstack"}:
            errors.append(f"{ticket_id}.route must be api, front, or fullstack")
        state = entry.get("state")
        if state not in VALID_STATES:
            errors.append(f"{ticket_id}.state is invalid: {state!r}")
        attempts = entry.get("attempts", 0)
        if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 0:
            errors.append(f"{ticket_id}.attempts must be a non-negative integer")
        priority = entry.get("priority", 0)
        if not isinstance(priority, int) or isinstance(priority, bool):
            errors.append(f"{ticket_id}.priority must be an integer")

        for field in ("ticket_path", "plan_path", "branch"):
            if not isinstance(entry.get(field), str) or not entry.get(field, "").strip():
                errors.append(f"{ticket_id}.{field} must be a non-empty string")

        try:
            deps = _require_list(entry, "depends_on", ticket_id)
            conflict_ids = _require_list(entry, "conflicts_with", ticket_id)
            resources = _require_list(entry, "resources", ticket_id)
        except ManifestError as exc:
            errors.append(str(exc))
            deps, conflict_ids, resources = [], [], []

        if any(not isinstance(value, str) or not value for value in deps):
            errors.append(f"{ticket_id}.depends_on must contain non-empty strings")
        if any(not isinstance(value, str) or not value for value in conflict_ids):
            errors.append(f"{ticket_id}.conflicts_with must contain non-empty strings")
        if any(not isinstance(value, str) or not value for value in resources):
            errors.append(f"{ticket_id}.resources must contain non-empty strings")
        if len(deps) != len(set(deps)):
            errors.append(f"{ticket_id}.depends_on contains duplicates")
        if len(conflict_ids) != len(set(conflict_ids)):
            errors.append(f"{ticket_id}.conflicts_with contains duplicates")
        if len(resources) != len(set(resources)):
            warnings.append(f"{ticket_id}.resources contains duplicates")
        if ticket_id in deps:
            errors.append(f"{ticket_id} cannot depend on itself")
        if ticket_id in conflict_ids:
            errors.append(f"{ticket_id} cannot conflict with itself")
        for dependency in deps:
            if dependency not in ids:
                errors.append(f"{ticket_id} depends on unknown ticket {dependency}")
        for conflict_id in conflict_ids:
            if conflict_id not in ids:
                errors.append(f"{ticket_id} conflicts with unknown ticket {conflict_id}")

        dependencies[ticket_id] = deps
        conflicts[ticket_id] = conflict_ids

    for ticket_id, conflict_ids in conflicts.items():
        for conflict_id in conflict_ids:
            if conflict_id in conflicts and ticket_id not in conflicts[conflict_id]:
                warnings.append(
                    f"conflict is one-way: {ticket_id} -> {conflict_id}; scheduler still treats it as symmetric"
                )

    cycle = find_cycle(dependencies)
    if cycle:
        errors.append("dependency cycle: " + " -> ".join(cycle))

    return {"errors": errors, "warnings": warnings}


def find_cycle(dependencies: dict[str, list[str]]) -> list[str]:
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(ticket_id: str) -> list[str]:
        if ticket_id in visiting:
            start = stack.index(ticket_id)
            return stack[start:] + [ticket_id]
        if ticket_id in visited:
            return []
        visiting.add(ticket_id)
        stack.append(ticket_id)
        for dependency in dependencies.get(ticket_id, []):
            cycle = visit(dependency)
            if cycle:
                return cycle
        stack.pop()
        visiting.remove(ticket_id)
        visited.add(ticket_id)
        return []

    for ticket_id in dependencies:
        cycle = visit(ticket_id)
        if cycle:
            return cycle
    return []


def ensure_valid(data: dict[str, Any]) -> list[str]:
    result = validate_manifest(data)
    if result["errors"]:
        raise ManifestError("; ".join(result["errors"]))
    return result["warnings"]


def downstream_depths(tickets: dict[str, dict[str, Any]]) -> dict[str, int]:
    children: dict[str, list[str]] = {ticket_id: [] for ticket_id in tickets}
    for ticket_id, entry in tickets.items():
        for dependency in entry.get("depends_on", []):
            children[dependency].append(ticket_id)

    memo: dict[str, int] = {}

    def depth(ticket_id: str) -> int:
        if ticket_id not in memo:
            memo[ticket_id] = 1 + max((depth(child) for child in children[ticket_id]), default=0)
        return memo[ticket_id]

    return {ticket_id: depth(ticket_id) for ticket_id in tickets}


def conflict_pair(
    left_id: str,
    left: dict[str, Any],
    right_id: str,
    right: dict[str, Any],
) -> bool:
    if right_id in left.get("conflicts_with", []) or left_id in right.get("conflicts_with", []):
        return True
    return bool(set(left.get("resources", [])) & set(right.get("resources", [])))


def ready_tickets(data: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    ensure_valid(data)
    if limit < 1:
        raise ManifestError("limit must be at least 1")

    tickets = data["tickets"]
    max_repairs = data.get("policy", {}).get("max_repair_attempts", 2)
    depths = downstream_depths(tickets)
    active = [
        (ticket_id, entry)
        for ticket_id, entry in tickets.items()
        if entry["state"] in ACTIVE_STATES
    ]

    candidates: list[tuple[str, dict[str, Any]]] = []
    for ticket_id, entry in tickets.items():
        state = entry["state"]
        if state not in {"PENDING", "REPAIR"}:
            continue
        if state == "REPAIR" and entry.get("attempts", 0) > max_repairs:
            continue
        if not all(
            tickets[dependency]["state"] in DEPENDENCY_COMPLETE_STATES
            for dependency in entry.get("depends_on", [])
        ):
            continue
        if any(conflict_pair(ticket_id, entry, active_id, active_entry) for active_id, active_entry in active):
            continue
        candidates.append((ticket_id, entry))

    candidates.sort(
        key=lambda item: (
            -item[1].get("priority", 0),
            -depths[item[0]],
            item[0],
        )
    )

    selected: list[tuple[str, dict[str, Any]]] = []
    for ticket_id, entry in candidates:
        if any(conflict_pair(ticket_id, entry, chosen_id, chosen) for chosen_id, chosen in selected):
            continue
        selected.append((ticket_id, entry))
        if len(selected) == limit:
            break

    return [
        {
            "ticket_id": ticket_id,
            "state": entry["state"],
            "route": entry["route"],
            "branch": entry["branch"],
            "critical_depth": depths[ticket_id],
            "priority": entry.get("priority", 0),
        }
        for ticket_id, entry in selected
    ]


def transition_ticket(
    data: dict[str, Any],
    ticket_id: str,
    new_state: str,
    base_ref: str | None,
    branch: str | None,
    verdict: str | None,
    commit: str | None,
    error: str | None,
) -> dict[str, Any]:
    ensure_valid(data)
    tickets = data["tickets"]
    if ticket_id not in tickets:
        raise ManifestError(f"unknown ticket: {ticket_id}")
    if new_state not in VALID_STATES:
        raise ManifestError(f"invalid target state: {new_state}")

    entry = tickets[ticket_id]
    old_state = entry["state"]
    if new_state not in TRANSITIONS[old_state]:
        raise ManifestError(f"invalid transition for {ticket_id}: {old_state} -> {new_state}")

    if new_state == "RUNNING":
        incomplete = [
            dependency
            for dependency in entry.get("depends_on", [])
            if tickets[dependency]["state"] not in DEPENDENCY_COMPLETE_STATES
        ]
        if incomplete:
            raise ManifestError(
                f"{ticket_id} has incomplete dependencies: {', '.join(incomplete)}"
            )
        max_repairs = data.get("policy", {}).get("max_repair_attempts", 2)
        if old_state == "REPAIR" and entry.get("attempts", 0) > max_repairs:
            raise ManifestError(f"{ticket_id} exhausted repair attempts")
        for active_id, active_entry in tickets.items():
            if active_id != ticket_id and active_entry["state"] in ACTIVE_STATES:
                if conflict_pair(ticket_id, entry, active_id, active_entry):
                    raise ManifestError(f"{ticket_id} conflicts with active ticket {active_id}")
        entry["attempts"] = entry.get("attempts", 0) + 1
        if not base_ref:
            raise ManifestError("RUNNING transition requires --base-ref")

    if new_state == "REPAIR":
        max_repairs = data.get("policy", {}).get("max_repair_attempts", 2)
        if entry.get("attempts", 0) > max_repairs:
            raise ManifestError(f"{ticket_id} exhausted repair attempts; transition it to FAILED")

    if verdict is not None and verdict not in {"PASS", "FAIL", "INCONCLUSIVE"}:
        raise ManifestError(f"invalid verdict: {verdict}")
    if new_state == "VERIFIED" and verdict != "PASS":
        raise ManifestError("VERIFIED transition requires --verdict PASS")
    if new_state == "INTEGRATED" and entry.get("verdict") not in data.get("policy", {}).get(
        "integrate_on", ["PASS"]
    ):
        raise ManifestError(
            f"{ticket_id} verdict {entry.get('verdict')!r} is not allowed for integration"
        )

    entry["state"] = new_state
    if base_ref is not None:
        entry["base_ref"] = base_ref
    if branch is not None:
        entry["branch"] = branch
    if verdict is not None:
        entry["verdict"] = verdict
    if error is not None:
        entry["last_error"] = error
    elif new_state not in {"REPAIR", "BLOCKED", "FAILED"}:
        entry["last_error"] = None
    if commit is not None:
        entry.setdefault("commits", {})[new_state.lower()] = commit
    entry.setdefault("history", []).append(
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "from": old_state,
            "to": new_state,
            "commit": commit,
            "error": error,
        }
    )
    return entry


def manifest_summary(data: dict[str, Any]) -> dict[str, Any]:
    warnings = ensure_valid(data)
    tickets = data["tickets"]
    counts = Counter(entry["state"] for entry in tickets.values())
    blocked_by: dict[str, list[str]] = {}
    for ticket_id, entry in tickets.items():
        incomplete = [
            dependency
            for dependency in entry.get("depends_on", [])
            if tickets[dependency]["state"] not in DEPENDENCY_COMPLETE_STATES
        ]
        if incomplete and entry["state"] == "PENDING":
            blocked_by[ticket_id] = incomplete
    return {
        "batch_id": data["batch_id"],
        "target_branch": data["target_branch"],
        "counts": dict(sorted(counts.items())),
        "blocked_by": blocked_by,
        "warnings": warnings,
    }


def sample_manifest() -> dict[str, Any]:
    def ticket(
        ticket_id: str,
        dependencies: list[str] | None = None,
        resources: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "ticket_path": f"docs/tickets/{ticket_id}.md",
            "plan_path": f"docs/plans/{ticket_id}_plan.md",
            "route": "api",
            "branch": f"feature/{ticket_id.lower()}",
            "depends_on": dependencies or [],
            "conflicts_with": [],
            "resources": resources or [],
            "priority": 0,
            "state": "PENDING",
            "attempts": 0,
            "base_ref": None,
            "verdict": None,
            "commits": {},
            "last_error": None,
            "history": [],
        }

    return {
        "schema_version": 1,
        "batch_id": "self-test",
        "target_branch": "dev",
        "policy": {
            "max_repair_attempts": 2,
            "integrate_on": ["PASS"],
            "push_mode": "batch-end",
        },
        "tickets": {
            "T1": ticket("T1"),
            "T2": ticket("T2"),
            "T3": ticket("T3", ["T2"]),
            "T4": ticket("T4", ["T3"]),
            "T5": ticket("T5", resources=["table:users"]),
            "T6": ticket("T6", resources=["table:users"]),
        },
    }


def self_test() -> dict[str, Any]:
    data = sample_manifest()
    assert not validate_manifest(data)["errors"]

    ready = ready_tickets(data, 3)
    ready_ids = [item["ticket_id"] for item in ready]
    assert "T2" in ready_ids, "the head of the longest chain should be ready"
    assert not ({"T5", "T6"} <= set(ready_ids)), "resource conflicts must not share a ready set"

    transition_ticket(data, "T2", "RUNNING", "abc123", None, None, None, None)
    assert data["tickets"]["T2"]["attempts"] == 1
    transition_ticket(data, "T2", "IMPLEMENTED", None, None, None, "impl1", None)
    transition_ticket(data, "T2", "VERIFYING", None, None, None, None, None)
    transition_ticket(data, "T2", "VERIFIED", None, None, "PASS", "verify1", None)
    transition_ticket(data, "T2", "INTEGRATING", None, None, None, None, None)
    transition_ticket(data, "T2", "INTEGRATED", None, None, None, "dev1", None)
    assert "T3" in [item["ticket_id"] for item in ready_tickets(data, 6)]

    cycle_data = sample_manifest()
    cycle_data["tickets"]["T2"]["depends_on"] = ["T4"]
    assert validate_manifest(cycle_data)["errors"], "cycle must be rejected"

    exhausted = sample_manifest()
    exhausted["policy"]["max_repair_attempts"] = 0
    transition_ticket(exhausted, "T1", "RUNNING", "abc123", None, None, None, None)
    try:
        transition_ticket(exhausted, "T1", "REPAIR", None, None, None, None, "failed")
        raise AssertionError("exhausted repairs must be rejected")
    except ManifestError:
        pass

    with tempfile.TemporaryDirectory() as directory:
        duplicate_path = Path(directory) / "duplicate.json"
        duplicate_path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
        try:
            load_manifest(duplicate_path)
            raise AssertionError("duplicate JSON keys must be rejected")
        except ManifestError:
            pass

    return {
        "status": "PASS",
        "checks": [
            "schema validation",
            "critical-chain readiness",
            "resource conflict exclusion",
            "state transitions",
            "dependency unlock",
            "cycle rejection",
            "repair budget enforcement",
            "duplicate JSON key rejection",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="validate a manifest")
    validate_parser.add_argument("manifest", type=Path)

    ready_parser = subparsers.add_parser("ready", help="select runnable tickets")
    ready_parser.add_argument("manifest", type=Path)
    ready_parser.add_argument("--limit", type=int, required=True)

    transition_parser = subparsers.add_parser("transition", help="apply a state transition")
    transition_parser.add_argument("manifest", type=Path)
    transition_parser.add_argument("ticket_id")
    transition_parser.add_argument("new_state")
    transition_parser.add_argument("--base-ref")
    transition_parser.add_argument("--branch")
    transition_parser.add_argument("--verdict")
    transition_parser.add_argument("--commit")
    transition_parser.add_argument("--error")

    summary_parser = subparsers.add_parser("summary", help="summarize a manifest")
    summary_parser.add_argument("manifest", type=Path)

    subparsers.add_parser("self-test", help="run built-in scheduler tests")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "self-test":
            result = self_test()
        else:
            data = load_manifest(args.manifest)
            if args.command == "validate":
                result = validate_manifest(data)
                result["valid"] = not result["errors"]
                if result["errors"]:
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                    return 1
            elif args.command == "ready":
                result = {"ready": ready_tickets(data, args.limit)}
            elif args.command == "transition":
                entry = transition_ticket(
                    data,
                    args.ticket_id,
                    args.new_state,
                    args.base_ref,
                    args.branch,
                    args.verdict,
                    args.commit,
                    args.error,
                )
                save_manifest(args.manifest, data)
                result = {"ticket_id": args.ticket_id, "ticket": entry}
            elif args.command == "summary":
                result = manifest_summary(data)
            else:
                parser.error(f"unknown command: {args.command}")
                return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except ManifestError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
