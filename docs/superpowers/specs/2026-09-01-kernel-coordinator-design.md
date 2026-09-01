# KERNEL Coordinator Design

## Goal

Add a local-first coordinator that safely selects and runs independent KERNEL tasks in bounded parallel batches while preserving dependency order, provider cost gates, leases, and evidence.

## Scope

The first slice covers local board scheduling only. It does not publish, commit, push, delete, manage credentials, or invoke paid providers without an existing approval record.

## Architecture

`Coordinator` reads the board through the existing kernel data model, computes dependency-ready tasks, orders providers by local cost and privacy, and starts at most `N` tasks. A filesystem lease under the board prevents two coordinator processes from starting the same task. Every state transition is appended to `events.jsonl`.

The existing `run-safe` command remains compatible. A new `run-ready --workers N` command uses the coordinator and defaults to a dry local execution record until a provider executor is configured.

## Safety rules

- Only tasks with all dependencies verified or published are eligible.
- Active, verified, published, blocked, rejected, and failed tasks are excluded from a new batch.
- A task lease expires only after an explicit stale-lease timeout; active leases are never silently replaced.
- Provider order is local, then configured free providers, then Freebuff, then approved paid providers.
- Paid providers require `approved: true` and retain their declared spend limit.
- No task is marked verified without explicit evidence.
- Event records are append-only and include task, provider, and lease identity where applicable.

## Interfaces

`Coordinator(board_root, workers=1, lease_seconds=300)`

- `ready_tasks() -> list[dict]`
- `provider_order(task) -> list[str]`
- `claim(task_id) -> bool`
- `release(task_id)`
- `run_batch() -> dict`

The CLI command `run-ready` returns JSON containing selected task IDs, skipped task IDs with reasons, worker limit, and zero or more execution errors.

## Testing

Tests must cover dependency readiness, worker limits, lease conflicts, provider ordering, paid-provider approval, and event recording. Existing CLI behavior must remain green.

## Non-goals

This slice does not implement remote orchestration, browser synchronization, model selection, automatic retries, or external plugin installation. Those remain later designs requiring separate approval.

