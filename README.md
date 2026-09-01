# KERNEL

KERNEL is a local-first Codex plugin for coordinating registered ecosystem work while preserving each project's identity, ownership, authority, and data boundary.

## Current capabilities

- dependency-aware task selection
- bounded parallel local execution
- explicit executable allowlists with `shell=False`
- timeouts and cancellation
- stale lease recovery
- content-addressed caching of successful commands
- append-only structured execution events
- provider ordering: local, configured free, Freebuff, then approved paid providers
- evidence-based task states; staging is not verification

The board is created wherever `--board` points (default: `.kernel`). It stores projects and tasks in `board.json`, leases and cache entries under the board directory, and execution evidence in `events.jsonl`.

## Quick start

```text
python scripts/kernel.py --board .kernel status
python scripts/kernel.py --board .kernel scan --root <project>
python scripts/kernel.py --board .kernel next
python scripts/kernel.py --board .kernel run-ready --workers 2
python -m pytest tests
```

The Python coordinator API is in `scripts/coordinator.py`. `execute()` accepts an argv list and an explicit `allowed_executables` list. It never evaluates shell text. `execute_batch()` runs independent commands concurrently up to the configured worker limit.

## Operating boundary

KERNEL prefers local execution. Remote providers, paid work, commits, pushes, publishing, deletion, credentials, and canonical architecture changes remain approval-gated. KERNEL does not claim completion from a process, queue, configuration, or staging state; fresh execution evidence is required.

## Development

The project targets Python 3.10–3.12 and runs the same test suite in GitHub Actions. Generated board data and test scratch directories are ignored by Git. See `docs/superpowers/specs/2026-09-01-kernel-coordinator-design.md` for the coordinator design and the per-directory README files for data contracts.
