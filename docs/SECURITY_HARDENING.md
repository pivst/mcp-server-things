# Fork security hardening

Baseline: upstream `22cc5c61ae70b6fb1c115c27c66e45154fa66190` (1.10.0).
The upstream default branch matched this reviewed release when work began.

## Changes

- Escape dynamic IDs, list/date strings and echoed IDs at AppleScript generation
  boundaries, including move destinations, update-project, update-todo, tags,
  bulk updates, scheduling fallbacks, search lists and configured app names.
  Unsupported controls are rejected instead of silently changing identifiers;
  quotes, backslashes, CR, LF and TAB round-trip through string literals.
- Quote the URL at both shell and AppleScript boundaries and require the Things
  URL scheme. This also covers the internal URL override path.
- Execute scripts once by default. A failure, timeout or in-script error may
  follow a partial write; return `OUTCOME_UNCERTAIN`, not automatic replay.
  `retry_safe=True` is an internal, explicit opt-in for callers that establish
  read-only/idempotent behavior. Only the availability probe opts in currently.
  All public mutation responses preserve a structured uncertainty marker and
  `retry_safe=False`; scheduling/deletion fallback chains stop immediately,
  including per-format date retries and follow-up writes after creation.
  Bulk operations preserve uncertainty at the top level. Users must inspect state
  before retrying. This prevents automatic duplicates, not exactly-once delivery.
- Stop tag replacement if the existing-tag query fails or has no valid output.

The injection threat is a malicious argument reaching a tool's code-generation
boundary. Merely reading a malicious task title does not execute that title.

## Verification

All tests use mocks or guarded subprocess boundaries. No live Things test,
installation, permission grant, token configuration or HTTP listener was used.

```sh
PYTHONPATH=tests/safety:src THINGSDB=/tmp/nonexistent-things-test.sqlite \
  .venv/bin/pytest tests/unit
.venv/bin/python -m build --wheel --no-isolation
```

The optional `tests/safety/sitecustomize.py` guard refuses real Things process
execution and private user Library/config reads. It should be on PYTHONPATH
before imports; it is an extra test safeguard, not a production sandbox.

- Baseline unit suite: 2,222 passed, 1 packaging test skipped.
- Final unit suite: 2,358 passed, 1 packaging test skipped.
- Added security regressions: 136 cases, including control-character boundaries,
  valid source plus malicious destination, database-unavailable fallbacks,
  tag-read failure and public create-project timeout (one dispatch only).
  A 29-case public-facade suite exercises the real executor with mocked
  subprocesses across creation, updates, areas, tags, checklists, moves, bulk
  updates and scheduling. It verifies terminal uncertainty with no fallback
  dispatch, including a successful first write followed by a timed-out write.
- Packaging pytest skips because its isolated pip build cannot fetch build
  dependencies in the restricted environment. The separate wheel build with
  preinstalled, declared build dependencies succeeds.
- Integration suite: all 122 cases skipped in both baseline and fixed checkout
  because live testing is opt-in. No live test result is claimed.
- `git diff --check` passes. Focused flake8/Black/isort checks on the executor,
  new security tests, uncertainty helper and test guard pass, using the project's intended E501/W503
  exclusions for flake8.
- Repository-wide flake8 and isort are already failing upstream. With E501
  excluded as intended by pyproject.toml, flake8 has the same 1,321 diagnostics
  before/after. Bare flake8 does not read that TOML configuration and additionally
  flags line lengths, including some changed interpolation lines.
- Stock mypy is blocked by the obsolete Python 3.8 target with current
  dependencies. With `--python-version 3.14`, both baseline and fixed checkout
  report the same 136 errors in 19 files; no new diagnostic was introduced.
- The repository-wide Black command selects no files because of the existing
  include configuration; explicit-file checks above provide meaningful evidence.
- Beads (`bd`) is unavailable locally; no upstream issues or tracker data changed.

## Remaining limits and connection prerequisites

This is a focused repair, not a complete dependency/security audit. Existing
HTTP authentication exposure, default note inclusion, token auto-discovery and
sensitive debug logging behavior remain outside this patch. Keep any later
connection on local stdio, disable debug logging, and review data/tool exposure.
Do not grant broad system permissions as a substitute for verification.

Before switching the existing reminder workflow, pin the reviewed fork commit
and verify that a fresh delegated task can discover and call native MCP tools.
Configuration presence alone is not proof of connectivity. Start with capability
and read-only probes; separately validate write behavior and preserve the
existing notification deduplication protocol. No MCP integration is enabled by
this commit.

The initial pushed commit `01b0b0d` had zero Actions runs, zero check runs and
zero commit statuses when queried. No hosted CI was enabled or requested.
Local validation above is the evidence; hosted CI success is not claimed.
