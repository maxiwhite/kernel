---
name: kernel
description: Coordinate canonical project work, safe execution, provider routing, budget gates, and verification through KERNEL.
---

# KERNEL

Use `scripts/kernel.py` with a board directory to scan projects, select dependency-ready work, route safe work through local/Freebuff/free providers, record Oracle-readable events, and verify evidence.

Never claim completion without verification evidence. Paid providers, commits, pushes, publishing, deletion, credentials, and canonical architecture changes require explicit user approval.

Typical commands:

```text
python scripts/kernel.py status
python scripts/kernel.py scan --root <project>
python scripts/kernel.py next
python scripts/kernel.py run-safe <task-id> --provider local
python scripts/kernel.py verify <task-id> --evidence "tests passed"
python scripts/kernel.py provider-health
python scripts/board_view.py --board <board> --output "KERNEL Board.html"
```

The board view is a local, human-readable HTML report. It does not send board data anywhere.

