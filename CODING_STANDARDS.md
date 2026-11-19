# Coding standards

These rules need judgement, so no linter or test checks them. A reviewer checks every change against them.

## Commit prefix

Use `refactor:` only for a commit that changes no visible behavior. If the commit message lists a behavior change, the
commit is `fix:` or `feat:`. For example, a06f311 changed which screen is painted first and was wrongly `refactor:`.

## Glossary vocabulary

New identifiers, view fields and messages use the terms in `GLOSSARY.md`. Never use a term the glossary lists under
_Avoid_. For example, `connection_error` was renamed `wheel_link_error` because the glossary avoids "connection screen".

## Regression tests fail without the fix

A commit that adds or changes a regression test records, in its message, the `scripts/red-at.py` run of that version
of the test against code without the fix: the base ref, the runs failed there and the runs passed in the working tree.
A later commit that reworks the test records a new run. For example, #75's reworked `overtaken_export` passed on the
unfixed frontend too, and only a re-run against `a171e1e` showed it.

## Shared watch test helpers

When two watch suites use a helper, it lives in `watch/tests/harness.cjs`. Suites keep only their scenarios and
assertions, and no suite imports another suite.

## Shared Python test helpers

When two Python test modules or browser flows use a helper, it lives in `tests/support.py`, as `load_script` (for the
hyphenated `scripts/*.py`) and `sha256` do. Test files import from `support` and never from one another.
