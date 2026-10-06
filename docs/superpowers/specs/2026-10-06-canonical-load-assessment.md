# Canonical Load Assessment

## Purpose

KERNEL already coordinates execution. This layer adds the missing operator-control surface:
reduce concurrent work to a bounded view, expose dependency pressure, flag likely duplicate work,
and measure context cost only when a producer supplies an actual measurement.

It does not create a second scheduler, second project registry, or second memory system.

## Canonical ownership

- **Uniformity**: portfolio truth, cross-system identity, dependency/state projection.
- **Hermes**: operator routing, delegation, verification, human-facing next action.
- **KERNEL**: local execution, leases, bounded concurrency, provider/cost gates, cache, append-only execution evidence, load assessment.
- **Domain systems**: own domain state and domain evidence.
- **Fridge Brain**: diagnostic reasoning and workshop evidence; it does not become the portfolio scheduler.
- **RESELL / SUBANGEL / LOGARHYTHM**: remain domain boundaries and only exchange explicit contracts.

## Assessment states

NOW = one actively consuming execution slot.

NEXT = up to three dependency-ready items that can safely become the next work.

WAITING = work whose dependency is not verified/published.

BLOCKED = work that cannot proceed because of an explicit failure, rejection, or block.

PARKED = valid work that is not currently consequential enough to compete for attention.

Overflow remains visible as evidence, not as another queue.

## Duplicate-work detection

KERNEL computes a deterministic fingerprint from project identity plus normalized task title.
A duplicate candidate is a signal, not an automatic merge. The operator must inspect whether
the tasks actually represent the same work before consolidation.

The canonical rule is:

discover once -> record once -> reuse the evidence everywhere appropriate.

Do not repeatedly rediscover the same repository state, architecture decision, test result,
or source document in each domain.

## Context-cost measurement

The assessment surface accepts optional estimated_tokens and context_cost fields.
It reports only values actually supplied by instrumentation.

It must never infer or fabricate provider billing/token usage.

Next instrumentation target: record context-cost receipts at Hermes/KERNEL boundaries so we can
compare repeated retrieval, repeated summarization, and repeated decision context.

## Dependency implementation order

1. KERNEL assessment primitive (this slice).
2. Hermes consumes the assessment instead of maintaining another work queue.
3. Uniformity supplies canonical project/dependency projections.
4. Add cross-system evidence receipts and identity references.
5. Instrument context cost and repeated retrieval.
6. Use measured duplication to remove redundant work.
7. Only then add broader automation or additional agent capacity.

## Release gate

The layer is useful when:

- one operator view identifies the current work without reading every project;
- dependencies explain why work is waiting;
- duplicate candidates are visible without destructive auto-merges;
- no new scheduler or memory store is introduced;
- measured context cost can be traced to a source event;
- the Golden Loop remains the release gate for physical/workshop functionality.

## Explicit non-goals

No new LLM, no new plugin, no autonomous task deletion, no automatic cross-repository merging,
no replacement of Uniformity, and no claim that ChatGPT billing/token totals are measured until
a real provider receipt exists.
