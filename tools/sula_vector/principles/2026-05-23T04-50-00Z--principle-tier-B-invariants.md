---
id: 2026-05-23T04-50-00Z--principle-tier-B-invariants
time: 2026-05-23T04:50:00Z
kind: principle
tier: invariant
tags: [sula-principle, immutable]
---
Core invariants. All must hold at all times.

B1. No mutation. Append-only. Past fragments are immutable.
B2. No implicit state. Anything that affects render output must be a named fragment.
B3. `kind` is a free-form string. No central enumeration of kinds. New scenarios add strings, not dimensions.
B4. No daemon, no kernel directory, no cache-as-truth, no central catalog.
B5. Given the same (fragments, conventions), the rendered view is byte-stable.
B6. Any LLM, any device, two-step boot: read AGENTS.md, run `render --for-agent`. Anything more required is a leak.
B7. The substrate (git / Drive / filesystem) handles storage and concurrency. Sula does not invent its own.
B8. Important context must land in fragments. Conversation transcripts alone do not count as durable memory.
B9. Goals must carry a verifier. Ambition without verification is a wish, not a goal.
