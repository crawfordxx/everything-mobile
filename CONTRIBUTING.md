# Contributing to everything-mobile

Thanks for your interest. Before you spend time, please read the README's "What this is NOT" section. PRs that fall into those categories will be closed without review.

## Pre-PR checklist

```bash
ruff check src tests
ruff format --check src tests
mypy
pytest tests/unit -v
EM_INTEGRATION=1 pytest tests/integration -v   # requires a real device
```

All four must pass. CI runs the first three on every PR.

## New verb requirements

If you're adding a verb to an existing plugin or a new plugin:

- [ ] **Unit test** with a fixture XML (drop a copy of the relevant UI dump under `tests/fixtures/`)
- [ ] **Integration test** marked `@pytest.mark.integration` that runs on a real device
- [ ] **Selectors** prefer semantic `resource-id` over obfuscated 3-char rids. If you must use the obfuscated kind, document the fragility in a comment.
- [ ] **Verbs that mutate state** (post / send / submit) MUST use `requires_commit_flag=True` so the framework adds `--commit` + `EM_ALLOW_COMMIT=1` gating.
- [ ] **No template marketing text** in defaults, examples, or fixtures.
- [ ] **No credentials, account IDs, or personal data** committed.

## Code style

- Python 3.10+, type-annotated, ruff + mypy strict.
- File size target ≤ 400 lines, hard cap 800. Split by responsibility, not by technical layer.
- `from __future__ import annotations` on all source files.
- Subprocess is **only** allowed in `src/mobilecli/adb/device.py`. Anywhere else, go through `Device`.

## Test design

- Unit tests should be **deterministic and offline**. No `time.sleep`, no `subprocess`, no network.
- Integration tests gate behind `EM_INTEGRATION=1`. They get to use the real device.
- E2E tests (verbs that actually send) gate behind both `EM_E2E=1` and `EM_ALLOW_COMMIT=1`. They never run in CI.

## Adding selectors

When you find a UI selector for a verb:

1. Capture the relevant screen via `adb -s <serial> shell uiautomator dump --compressed /sdcard/x.xml && adb pull /sdcard/x.xml research/ui-trees/<app>/NN-<screen>.xml`
2. Also capture the screenshot: `adb -s <serial> exec-out screencap -p > research/ui-trees/<app>/NN-<screen>.png`
3. Update `research/ui-trees/<app>/00-selectors.md` with the new selector
4. Reference the file path in your code comment so the next maintainer can find it

## Behavior changes that touch safety

If you're touching `safety/humanize.py`, `safety/governor.py`, or `safety/linter.py`, your PR description must explain:

- What changed
- Why the previous behavior was wrong
- A citation from `docs/anti-risk-control.md` or an equivalent source
- Whether daily caps in plugins need to move in the same PR

## Signed commits

Sign commits with a real identity. Anonymous / `Co-Authored-By: random` PRs are closed.

## Code review

Every PR gets a codex review pass against `docs/superpowers/specs/2026-05-21-everything-mobile-design.md` before merge. If you want to run it yourself first:

```bash
codex exec --skip-git-repo-check "Review the PR diff against the spec and flag CRITICAL/HIGH issues"
```

## License

By contributing you agree your work is MIT-licensed. No CLA required.
