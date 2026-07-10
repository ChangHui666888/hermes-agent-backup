# Code Cleanup Reviewer Prompts

Use these goal templates with `delegate_task` batch mode when running the
post-edit code cleanup pass described in the "Post-Edit Code Cleanup (Simplify)"
section of `requesting-code-review`.

## Reviewer 1 — Code Reuse

> Review this diff for code that duplicates functionality already in the
> codebase. Search utility modules, shared helpers, and adjacent files
> (use search_files / grep) for existing functions, constants, or patterns
> the new code could call instead of reimplementing. Flag: new functions
> that duplicate existing ones; hand-rolled logic that an existing utility
> already does (manual string/path manipulation, custom env checks, ad-hoc
> type guards, re-implemented parsing). For each, name the existing thing to
> use and where it lives.

## Reviewer 2 — Code Quality

> Review this diff for quality problems. Look for: redundant state (values
> that duplicate or could be derived from existing state; caches that don't
> need to exist); parameter sprawl (new params bolted on where the function
> should have been restructured); copy-paste-with-variation (near-duplicate
> blocks that should share an abstraction); leaky abstractions (exposing
> internals, breaking an existing encapsulation boundary); stringly-typed
> code (raw strings where a constant/enum/registry already exists — check the
> canonical registries before flagging). For each, give the concrete refactor.

## Reviewer 3 — Efficiency

> Review this diff for efficiency problems. Look for: unnecessary work
> (redundant computation, repeated file reads, duplicate API calls, N+1
> access patterns); missed concurrency (independent ops run sequentially);
> hot-path bloat (heavy/blocking work on startup or per-request paths);
> TOCTOU anti-patterns (existence pre-checks before an op instead of doing
> the op and handling the error); memory issues (unbounded growth, missing
> cleanup, listener/handle leaks); overly broad reads (loading whole files
> when a slice would do). For each, give the concrete fix and why it's faster
> or lighter.
