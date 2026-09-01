# KERNEL

KERNEL is a local-first Codex plugin for coordinating Oracle ecosystem work.

Its board is created wherever `--board` points (default: `.kernel`). The board stores projects and tasks in `board.json`; append-only execution evidence is stored in `events.jsonl`.

Provider integrations are deliberately conservative: local, Freebuff, and explicitly configured free providers are eligible for safe execution; paid providers are refused until approval is recorded.
