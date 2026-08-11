---
id: 2026-05-23T04-50-00Z--principle-tier-E-anti-patterns
time: 2026-05-23T04:50:00Z
kind: principle
tier: anti-pattern
tags: [sula-principle, immutable]
---
Delete on sight. These are signs the wrong layer is being defended.

E1. Storing derived views as truth (status snapshots, indexes, catalogs as primary).
E2. Adding a new state directory beside `fragments/`.
E3. Editing or deleting past fragments. Even "cleanup" or "merge" — append a new fragment that refs the old instead.
E4. Centralizing the `kind` enumeration or central kind validation.
E5. Inventing a new substrate / runtime / daemon when an existing one already solves it.
E6. Wrapping fragments in a SaaS-shaped registry / orchestration / API surface.
E7. Splitting a file purely to satisfy a line count.
E8. Leaving decisions and context in chat transcripts only, never landed in fragments.
E9. Declaring a goal without a verifier.
