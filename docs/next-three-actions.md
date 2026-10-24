# Next Three Actions — conversation handoff contract (v1)

## Purpose

Offer **up to three** ranked, ready actions at the end of a relevant response, with the recommended next action first. Selecting one asks the assistant to begin that action in the current conversation; it **does not** silently launch commands, commit code, approve spending, or merge a PR.

## KERNEL reference implementation

`python -m scripts.next_three --input actions.json` consumes a JSON array of task objects or `{ "tasks": [...] }` and prints deterministic, inspectable JSON. It is **advisory only**; it does not mutate the board or execute actions. The existing coordinator remains the authority for execution and evidence. A future adapter can map verified KERNEL board entries into this schema.

Each action has: `id`, `title`, `prompt`, `project` (optional), `status` (`planned`/`ready` to offer), `depends_on` (optional list of IDs), `impact`, `urgency`, `effort` (1–5), `approval_required`, `approved`, `risk`, `risk_reviewed`. `prompt` must be a clear instruction with success criteria and relevant scope. Do not insert personal secrets or credentials into prompts.

The output contains `version`, `actions` (maximum three) and `skipped` with a reason. The first action is marked `recommended: true`. Blocked, draft, completed, dependency-unmet, unapproved or unreviewed high-risk tasks are not offered. Rank = impact×5 + urgency×3 − effort×2; lower effort and lexical ID break ties. Selection does not equal approval or task completion.

## ChatGPT client renderer contract

For supported ChatGPT messages, render up to three genuine clickable controls, the recommended action first. For each action, use `GenUI.issueNewTurn(action.prompt)` only in a user-click handler. Clicking triggers a new conversational request; the assistant must re-check current state, permissions, safety, dependencies, CI, and evidence before any writes.

Illustrative rendering (this Python module does not inject UI into ChatGPT):

```jsx
<button onClick={() => GenUI.issueNewTurn("Inspect the RESELL PR, verify tests and reviews, then merge if safe; report SHA.")}>1. Verify & merge RESELL PR</button>
<button onClick={() => GenUI.issueNewTurn("Audit the 14-second RESELL landing experience on mobile and list issues.")}>2. Audit mobile intro</button>
<button onClick={() => GenUI.issueNewTurn("Connect KERNEL next-three output to Hermes without modifying unrelated projects.")}>3. Connect Hermes</button>
```

Only show actions for feasible operations; if access is missing, offer an access-restoration or safe-handoff action, never an impossible merge. Keep the chosen task in focus and respect project boundaries.

## Installation boundary

This repository ships reusable **ranking logic and a UI handoff contract**, not an installed global ChatGPT extension. A host-level app/plugin integration and explicit user installation are needed to display it automatically across future conversations. A Git push alone cannot enable that behavior. Within a conversation, supported ChatGPT buttons can already submit follow-up requests.
