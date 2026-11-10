# Page67 readiness and next-agent handoff

## Scope

This checkout contains the integrated scanner changes documented in
`2026-11-08-open-prs.md`, including Kotlin package imports, implicit operator
imports, Gradle/test zoning, exclusions, and bounded ktlint autofix.

The final review corrected two additional Kotlin issues:

- Formatter stdin/stdout now explicitly use UTF-8, preventing Windows locale
  encoding from corrupting non-ASCII source. A real subprocess regression
  simulates a cp1252 host and UTF-8 tool; it failed before the fix and passed after.
- Explicit import bindings, including aliases, take precedence over inferred
  same-package/wildcard matches. Its regression also failed before the fix.

Kotlin remains a shallow language plugin. Its dependency graph approximates
name use; local shadowing, source-set visibility, generated code and reflection
can affect findings. Confirm dependency, orphan and coverage claims against the
actual Kotlin/Android code before changing behavior or deleting code.

## Verification on 2026-11-10

- Targeted Kotlin, generic tool, autofix, exclusion, lifecycle and CI-contract
  checks: **248 passed, 5 skipped**. The skips require the real ktlint executable,
  which is absent from this native Windows test environment.
- Ruff CI gate passed; configured mypy gate passed (16 files); import contract
  passed (1 kept, 0 broken); `git diff --check` passed.
- Read-only Page67 discovery/graph smoke check: **289 Kotlin files, 1,018 edges**;
  MainActivity, Page67App and both benchmark activities recognized as Android
  entry points. Build outputs and local agent worktrees excluded. This exercised
  discovery and the graph builder using absolute source paths; it was not a
  complete scan or an Android build.
- Full native Windows/Python 3.14 run: **7,906 passed, 31 skipped, 40 failed**.
  Thirty failures match the previously recorded Windows baseline. Nine additional
  failures pass when rerun with normal system temporary paths: putting fixtures
  beneath the git-ignored `.integration/` directory changes discovery behavior.
  The remaining additional failure is a locale-dependent Markdown round-trip
  assertion, also reproduced on untouched fork main (`b03d575f`). No new regression
  from these Kotlin fixes was identified. This is not an all-green Windows suite.
- Full-run XML/logs and baseline comparison are retained locally beneath ignored
  `.integration/` (`recheck-full-native-20261110.*`, `readiness-baseline-tests.xml`).
  The previous passing Linux full/core CI result is recorded in the November 8
  report; Linux CI was not rerun for this final review.

No Page67 source or scanner state was modified by this review.

## Prompt for the next agent

```text
Improve the Kotlin Android app Page67 using the verified local Desloppify fork.

App: C:\Programs\cygwin64\home\zlum1\src\page67
Scanner: C:\Programs\cygwin64\home\zlum1\src\desloppify (local main)

Work from the app root. Read AGENTS.md, CLAUDE.md, docs/STATUS.md,
docs/PERFORMANCE-HANDOFF.md and relevant app skills first. Preserve existing
user work, app behavior, purchases, saved data, translations and release setup.

Read the scanner's dev/integration/2026-11-10-page67-handoff.md, docs/SKILL.md
and docs/CODEX.md for the workflow and Kotlin limitations. Install this LOCAL
checkout into a dedicated Python 3.11+ environment with:
  python -m pip install -e "C:/Programs/cygwin64/home/zlum1/src/desloppify[full]"
Use that environment's python -m desloppify for every scanner command. Confirm
the imported package resolves to this checkout; do not replace it with PyPI.
Use the declared tree-sitter-language-pack<1.0 dependency. Check whether ktlint
is available before relying on its scan/autofix results, and report missing tools.

Keep .desloppify/ ignored and preserve existing scanner state. Inspect existing
configuration before scanning. Exclude generated/build/cache output and local
agent worktrees (.claude/worktrees etc.); keep production and test sources in
scope. Run `python -m desloppify --lang kotlin scan --path .`, then `next`.
If scan is gated by an existing cycle, inspect status/next and follow that cycle
without resetting state or bypassing the gate just to improve scores.

Follow next -> investigate -> fix -> verify -> resolve -> next. Prioritize real,
high-impact improvements. Verify heuristic findings manually, especially orphan,
dependency and coverage claims. Preview autofix and inspect its diff. Do not
suppress findings, weaken tests or change scoring to manufacture progress.

Run the app's documented JVM tests, debug build and Android lint for app changes;
use device/UI/performance checks when the change needs them. Keep improvements
reviewable, update docs/STATUS.md and the code map when required, and commit
verified work according to the app's instructions. Do not publish, upload a
release, change phone data or push without authorization. Finish with the actual
verification results, remaining issues and a clear continuation note.
```
