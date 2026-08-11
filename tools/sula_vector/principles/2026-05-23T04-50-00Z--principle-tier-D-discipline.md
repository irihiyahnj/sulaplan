---
id: 2026-05-23T04-50-00Z--principle-tier-D-discipline
time: 2026-05-23T04:50:00Z
kind: principle
tier: discipline
tags: [sula-principle, immutable]
---
Implementation discipline. When writing renderers, adapters, and tools.

D1. Standard library only when reasonable. No mandatory third-party dependencies.
D2. Zero comments unless WHY is non-obvious (hidden constraint, workaround, non-obvious invariant).
D3. No TODO, no placeholder functions, no half-implementations.
D4. No backwards-compatibility shims. Change the code directly.
D5. No claim of done without verification. Build / tests / byte-stable replay must pass where applicable.
