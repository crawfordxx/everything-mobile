# Plugin authoring guide

`mobilecli` discovers two kinds of app plugins:

1. **Built-in** — Python modules under `mobilecli.apps.*` (e.g. `mobilecli.apps.douyin`)
2. **External** — packages that register an `App` object under the `mobilecli.apps` entry-points group

The framework calls each plugin's verbs with `(args, ctx)` where `ctx` is an `ExecContext`. Layer 2.5 humanization, governor, and linter are pre-wired into `ctx` — you cannot bypass them from plugin code.

## Minimal external plugin

```
mobilecli-myapp/
├── pyproject.toml
└── src/mobilecli_myapp/__init__.py
```

`pyproject.toml`:

```toml
[project]
name = "mobilecli-myapp"
version = "0.1.0"
dependencies = ["everything-mobile"]

[project.entry-points."mobilecli.apps"]
myapp = "mobilecli_myapp:app"
```

`src/mobilecli_myapp/__init__.py`:

```python
from mobilecli.plugin import App, ExecContext

app = App(
    name="myapp",
    package="com.example.myapp",
    daily_caps={"comment": 50, "like": 200},
    extra_lint_patterns=[],   # extra regex on top of the defaults
)


@app.verb("launch")
def launch(args, ctx: ExecContext) -> dict:
    ctx.app.launch()
    return {"foreground": ctx.app.foreground()}


def _search_args(p):
    p.add_argument("--keyword", required=True)


@app.verb("search", add_args=_search_args)
def search(args, ctx: ExecContext) -> dict:
    ctx.app.ensure_foreground()
    xml_path = ctx.ui.dump()["path"]
    # ... find selectors, ctx.input.tap_node(node), etc.
    return {"results": []}
```

Then:

```bash
pip install -e mobilecli-myapp/
mobilecli myapp launch
mobilecli myapp search --keyword test
```

## ExecContext surface

This is everything plugins can call. There's no escape hatch — if you need something not here, open an issue.

### `ctx.input`

| Method | Use |
|---|---|
| `tap_node(node)` | Humanized tap inside `node["bounds"]` (60% inner box) |
| `tap_xy(x, y)` | Humanized tap with ±8 px jitter on (x, y) |
| `swipe(start, end)` | Humanized swipe (bezier-shape telemetry, randomized duration) |
| `type_text(text)` | Humanized type (per-char delay for ASCII, ADBKeyboard for CJK) |
| `keyevent(code)` | Send keyevent (alias `back`/`home`/`enter`/... or numeric KEYCODE) |

### `ctx.ui`

| Method | Use |
|---|---|
| `dump(output_path=None)` | uiautomator dump; returns `{path, size}` |
| `find_by_resource_id(xml, rid)` | First matching node or `None` |
| `find_by_content_desc(xml, desc)` | First matching node or `None` |
| `find_by_text(xml, text)` | First matching node or `None` |
| `find_all_by_resource_id(xml, rid)` | List of nodes (for result grids) |
| `screenshot(output_path=None)` | Capture PNG; returns `{path, size, width, height}` |

A `node` dict has keys: `resource_id`, `content_desc`, `text`, `class`, `bounds`, `cx`, `cy`, `clickable`, `focused`.

### `ctx.app`

| Method | Use |
|---|---|
| `launch()` | Launch the plugin's package |
| `foreground()` | Current foreground `{package, activity}` |
| `ensure_foreground()` | Launch if not already foreground |

### `ctx.governor` + `ctx.linter`

You should call these **before** state-mutating actions:

```python
@app.verb("comment", add_args=..., requires_commit_flag=True)
def comment(args, ctx):
    ctx.linter.check_or_raise(args.text)       # → CONTENT_BANNED
    ctx.governor.check_or_raise("comment")     # → RATE_LIMITED

    # ... do the work, including ctx.input.tap_node(send_btn) only if --commit ...

    if args.commit:
        ctx.governor.record("comment")
    return {...}
```

## Verbs that send (real side effects)

If your verb actually changes state (post comment / send DM / submit form), use `requires_commit_flag=True`. The framework will then:

- Add a `--commit` arg to the verb's parser
- Reject the call unless `EM_ALLOW_COMMIT=1` is in the environment
- Wrap into a `COMMIT_REFUSED` envelope if the gate fails

Default path (no `--commit`) must be dry-run: build the action, find the send button, return its coordinates, do NOT tap it.

## Selectors: how to keep them stable

- **Prefer semantic resource-ids** when the app provides them (e.g. XHS `mSearchToolBarEt`). They survive minor releases.
- **Avoid obfuscated rids** (Douyin uses 3-char `q21`/`gl1` style — they change between releases). Pair with `content-desc` or class+position fallback.
- **Capture UI tree** of each screen you depend on. Save under `research/ui-trees/<app>/`. Then when the app updates, diff the trees to find what moved.
- **Counts often live in `content-desc`** (e.g. `评论3809，按钮`). Use a regex extractor, not literal string match.

## Daily-cap conventions

The library ships per-app `daily_caps` based on `docs/anti-risk-control.md`. When that doc updates, plugin defaults update in the **same PR**. Don't just bump caps because your script hit `RATE_LIMITED` — that's the system working.

## PR checklist for upstream contributions

- [ ] New verb has both fixture-based unit tests and a real-device integration test
- [ ] No banned use cases (see README's "What this is NOT")
- [ ] No hardcoded credentials, account IDs, or personal data in fixtures
- [ ] No marketing templates / 引流话术 in default values
- [ ] Caps come from `docs/anti-risk-control.md`, not made up
- [ ] Verbs that mutate state have `requires_commit_flag=True`

PRs adding "convenience" verbs that sidestep the safety layers will be closed without review.
