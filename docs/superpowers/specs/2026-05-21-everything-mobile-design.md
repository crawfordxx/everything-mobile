# everything-mobile — v1 Design Spec

- **Date:** 2026-05-21
- **Repo:** `/Users/crawford/workspace/everything-mobile`
- **Reference code (private, do not ship):** `(internal sample, not vendored)`
- **Test device:** Pixel-class Android, serial `EXAMPLE-SERIAL`, USB ADB

## 1. Goal & scope

Open-source CLI that lets external AI agents (Claude Code, Codex CLI, openclaw, etc.) drive physical Android phones. The library itself contains **no AI** — every command is a deterministic JSON-in / JSON-out subprocess invocation. AI lives in the calling tool (Claude / Codex) and reads screenshots / XML dumps the CLI produces.

### In-scope for v1

- ADB-backed device layer for physically connected Android phones.
- Generic primitives: `devices`, `screenshot`, `tap`, `swipe`, `type`, `dump`, `keyevent`, `launch`, `install`, `foreground`, `doctor`.
- Two reference app plugins, deep enough to demo:
  - `douyin` (com.ss.android.ugc.aweme): `launch`, `search`, `detail`, `comment` (real send under `--commit`).
  - `xiaohongshu` (com.xingin.xhs): `launch`, `search`, `detail`, `comment` (dry-run only — never sends in v1).
- Plugin system: built-in modules under `mobilecli.apps.*` plus external `entry_points` group `mobilecli.apps`.
- pipx-installable Python package, Python 3.10+.
- Doctor command for environment self-check.

### Out of scope for v1

- Cloud-phone backends (Alicloud / Volcano / etc.).
- Multi-device fan-out (`--all`).
- WeChat / 微信 plugin (风控太重, defer to v2).
- 闲鱼 / 携程 / 淘宝 / 京东 plugins (out — no installed apps on test device, and apkpure programmatic install was blocked by Cloudflare).
- Session / watch mode.
- Action recording & replay.
- AI loop inside the framework.

## 2. Architecture

Four layers, each only depends on the layer directly below it.

```
Layer 3 — App plugins              mobilecli.apps.douyin, mobilecli.apps.xiaohongshu
Layer 2 — Generic primitives       screenshot, input (tap/swipe/type/keyevent), ui (dump+parse), app (launch/install/fg), ime
Layer 1 — ADB device backend       Device class: serial selection, shell exec, push/pull, timeouts, error mapping
Layer 0 — External (not ours)      adb binary, the Android device, the calling AI tool
```

### Design rules

- The CLI is **stateless**. Every command is independent. The AI decides what comes next.
- App plugins MUST only call Layer 2. They MUST NOT shell out to adb directly or import subprocess.
- Layer 2 is the public Python API for plugin authors. Layer 1 is internal.
- Large artefacts (PNG, XML) are written to `/tmp/em-*.{png,xml}` and the CLI emits only the path in JSON. AI reads the file separately (Claude / Codex have native PNG vision and can read XML directly).

## 3. CLI surface

Root command: `mobilecli`.

### Global flags

| Flag | Meaning |
|---|---|
| `--serial SERIAL` | Required if more than one device is connected. Reads from env `EM_SERIAL` as fallback. |
| `--pretty` | Pretty-print JSON output (default is compact). |
| `--verbose` | Send debug logs to stderr. |
| `--timeout SEC` | Per-command timeout (default 30s). |

JSON is always the output format — there is no human-only mode.

### Primitives (Layer 2)

```
mobilecli devices                          List connected devices.
mobilecli screenshot [-o PATH]             Capture screen. Returns path to PNG.
mobilecli tap X Y                          Tap at absolute pixel coords.
mobilecli swipe X1 Y1 X2 Y2 [--duration]   Swipe gesture.
mobilecli type "文字"                       Type text. Chinese routes through ADBKeyboard broadcast.
mobilecli keyevent {back|home|enter|recent|menu}
mobilecli dump [-o PATH]                   uiautomator dump XML. Returns path.
mobilecli launch <package>                 Launch app via `monkey -p <pkg>`.
mobilecli install <apk_path>               adb install -r.
mobilecli foreground                       Current foreground package + activity.
mobilecli doctor                           Environment self-check.
```

### Douyin verbs

```
mobilecli douyin launch                    Launch + verify foreground.
mobilecli douyin search --keyword K [--limit N]
                                            Tap home search affordance → type K → submit → parse result list → JSON.
mobilecli douyin detail                    Assume current screen is a video detail. Parse like/comment/share counts.
mobilecli douyin comment --text T [--commit]
                                            Open comment panel, fill text. WITHOUT --commit: leave as dry-run, return what would happen.
                                            WITH --commit: actually press send. Requires EM_ALLOW_COMMIT=1 env.
```

### Xiaohongshu verbs

```
mobilecli xiaohongshu launch               Launch. If first launch lands on login wall, press back + relaunch once.
mobilecli xiaohongshu search --keyword K [--limit N]
mobilecli xiaohongshu detail
mobilecli xiaohongshu comment --text T     DRY-RUN ONLY in v1. No --commit flag. Send button is never pressed.
```

## 4. Plugin system

### Module layout

```
src/mobilecli/apps/
  __init__.py        Registers built-in plugins on import.
  douyin.py          Exposes `app = App(name="douyin", package="com.ss.android.ugc.aweme")` + @app.verb decorators.
  xiaohongshu.py     Same shape.
```

### Plugin contract

```python
from mobilecli.plugin import App
from mobilecli.plugin.ctx import ExecContext

app = App(name="douyin", package="com.ss.android.ugc.aweme")

@app.verb("search")
def search(args, ctx: ExecContext) -> dict:
    ctx.ensure_foreground()
    xml = ctx.ui.dump()
    node = ctx.ui.find_by_content_desc(xml, "搜索")
    ctx.input.tap_node(node)
    ...
    return {"keyword": args.keyword, "results": [...]}
```

- Verb function signature: `(args, ctx) -> dict`. Args is an argparse Namespace produced by the verb's own parser. Ctx is `ExecContext` (see §4.3).
- Verb returns a plain dict. The framework wraps it as `{"ok": True, "data": <dict>, ...}`.
- Raised exceptions are caught, mapped to error codes (see §5), wrapped as `{"ok": False, "error": {...}}`.

### ExecContext (the only thing plugins see)

```python
class ExecContext:
    device: Device              # Layer 1 handle (rarely used directly)
    input: InputModule          # tap, swipe, type, keyevent, tap_node
    ui: UiModule                # dump, find_by_*, parse_bounds, screenshot
    app: AppModule              # launch, foreground, ensure_foreground, is_installed
    ime: ImeModule              # set_adbkeyboard, restore_default
```

Plugins MUST go through ctx. No direct subprocess, no direct adb.

### Auto-discovery

1. Built-in: at startup, `mobilecli.apps` package's `__init__.py` imports every submodule and reads each module's exported `app` symbol into a global registry.
2. External: `importlib.metadata.entry_points(group="mobilecli.apps")` — any installed package that registers in pyproject.toml under that group is loaded.

```toml
# In a community plugin like mobilecli-tiktok:
[project.entry-points."mobilecli.apps"]
tiktok = "mobilecli_tiktok:app"
```

## 5. JSON output contract

### Success envelope

```json
{
  "ok": true,
  "command": "douyin.search",
  "device": "EXAMPLE-SERIAL",
  "elapsed_ms": 1843,
  "data": { /* verb-specific */ }
}
```

### Error envelope

```json
{
  "ok": false,
  "command": "douyin.search",
  "device": "EXAMPLE-SERIAL",
  "elapsed_ms": 234,
  "error": {
    "code": "ELEMENT_NOT_FOUND",
    "message": "search affordance not found on home screen",
    "hint": "run `mobilecli dump` to inspect current state; the home screen may have changed"
  }
}
```

### Error code dictionary (closed set for v1)

| Code | Meaning | Recovery hint |
|---|---|---|
| `NO_DEVICE` | adb finds no device | check USB / `adb devices` |
| `MULTIPLE_DEVICES` | >1 device, no --serial | pass `--serial XXX` or set `EM_SERIAL` |
| `ADB_TIMEOUT` | shell command exceeded timeout | device may be frozen, try `adb reboot` |
| `APP_NOT_INSTALLED` | target package not on device | `mobilecli install <apk>` |
| `APP_NOT_FOREGROUND` | wrong app in foreground | run `<app> launch` first |
| `ELEMENT_NOT_FOUND` | expected UI element missing | `dump` to inspect, UI may have changed |
| `IME_NOT_SET` | ADBKeyboard not active | `doctor` will reset it |
| `COMMIT_REFUSED` | tried real send without env gate | set `EM_ALLOW_COMMIT=1` |
| `UNKNOWN` | uncaught exception | check stderr with `--verbose` |

### Verb data shapes

```
screenshot: {"path": "/tmp/em-screen-<ts>.png", "size": 184320, "width": 1080, "height": 2400}
dump:       {"path": "/tmp/em-dump-<ts>.xml", "size": 48721}
devices:    {"devices": [{"serial": "EXAMPLE-SERIAL", "state": "device", "model": "Pixel 6"}]}
foreground: {"package": "com.ss.android.ugc.aweme", "activity": ".main.MainActivity"}

douyin.search:
  {"keyword": "短剧", "results": [
    {"index": 1, "title": "...", "author": "...", "cx": 540, "cy": 720}
  ]}

douyin.detail:
  {"likes": 12345, "comments": 678, "collects": 90, "shares": 12,
   "title": "...", "author": "..."}

douyin.comment (dry-run):
  {"dry_run": true, "text": "...", "send_button_cx": 1010, "send_button_cy": 2150}
douyin.comment (--commit):
  {"committed": true, "text": "...", "verified_visible": true}

xiaohongshu.search:
  {"keyword": "穿搭", "results": [
    {"index": 1, "title": "...", "author": "...", "cx": 270, "cy": 800}
  ]}

xiaohongshu.detail:
  {"likes": 0, "comments": 0, "collects": 0, "title": "...", "author": "..."}

xiaohongshu.comment (always dry-run in v1):
  {"dry_run": true, "text": "...", "send_button_cx": ..., "send_button_cy": ...}
```

### Encoding rules

- `ensure_ascii=False` — Chinese in JSON stays as Chinese, not `\uXXXX`.
- Compact by default. `--pretty` for human reading.
- UTF-8 stdout. Set `PYTHONIOENCODING=utf-8` in entry point.

## 6. Repository structure

```
everything-mobile/
├─ README.md
├─ LICENSE                       (MIT)
├─ pyproject.toml
├─ .github/workflows/ci.yml
├─ .gitignore
│
├─ docs/
│  ├─ quickstart.md
│  ├─ ai-usage.md                "how to drive this from Claude Code / Codex"
│  ├─ plugin-guide.md
│  └─ superpowers/specs/
│     └─ 2026-05-21-everything-mobile-design.md   (this file)
│
├─ src/mobilecli/
│  ├─ __init__.py
│  ├─ __main__.py
│  ├─ cli.py                     argparse root, dispatch to commands / app verbs
│  ├─ envelope.py                JSON envelope, error codes, elapsed_ms wrapper
│  │
│  ├─ adb/
│  │  ├─ __init__.py
│  │  ├─ device.py               Device class (Layer 1)
│  │  └─ errors.py
│  │
│  ├─ core/                      Layer 2 primitives
│  │  ├─ __init__.py
│  │  ├─ screenshot.py
│  │  ├─ input.py                tap/swipe/type/keyevent + tap_node helper
│  │  ├─ ui.py                   dump + find_by_text/content_desc/resource_id/class
│  │  ├─ app.py                  launch/install/foreground/ensure_foreground
│  │  └─ ime.py                  ADBKeyboard setup
│  │
│  ├─ plugin/                    Layer 3 framework
│  │  ├─ __init__.py
│  │  ├─ base.py                 App class, @verb decorator
│  │  ├─ registry.py             discovery (built-in + entry_points)
│  │  └─ ctx.py                  ExecContext
│  │
│  ├─ apps/                      Built-in plugins
│  │  ├─ __init__.py
│  │  ├─ douyin.py
│  │  └─ xiaohongshu.py
│  │
│  └─ commands/                  Top-level primitive commands
│     ├─ devices.py
│     ├─ screenshot.py
│     ├─ tap.py
│     ├─ swipe.py
│     ├─ type_cmd.py
│     ├─ dump.py
│     ├─ keyevent.py
│     ├─ launch.py
│     ├─ install.py
│     ├─ foreground.py
│     └─ doctor.py
│
├─ tests/
│  ├─ unit/                      Offline, fixture-driven
│  │  ├─ test_envelope.py
│  │  ├─ test_registry.py
│  │  ├─ test_xml_parse.py
│  │  └─ test_cli_dispatch.py
│  ├─ integration/               Real device, read-only verbs
│  │  ├─ test_primitives.py
│  │  ├─ test_douyin_readonly.py
│  │  └─ test_xiaohongshu_readonly.py
│  └─ fixtures/
│     └─ <subset of research/ui-trees/ XMLs as test inputs>
│
└─ research/
   └─ ui-trees/                  Captured 2026-05-21
      ├─ douyin/
      │  ├─ 00-selectors.md      Stable selector inventory
      │  └─ NN-*.{xml,png}
      └─ xiaohongshu/
         ├─ 00-selectors.md
         └─ NN-*.{xml,png}
```

## 7. v1 Definition of Done

- [ ] `pipx install -e .` works locally.
- [ ] `mobilecli doctor` reports all green on the test device.
- [ ] All 11 primitive commands return correctly-shaped JSON on the test device.
- [ ] `mobilecli douyin launch / search / detail` each succeed end-to-end on the test device.
- [ ] `mobilecli xiaohongshu launch / search / detail` each succeed end-to-end on the test device.
- [ ] `mobilecli douyin comment --text "..."` runs as dry-run by default; `--commit` with `EM_ALLOW_COMMIT=1` posts and verifies visibility.
- [ ] `mobilecli xiaohongshu comment --text "..."` runs as dry-run; no commit path exists.
- [ ] Unit test coverage ≥ 70% on `envelope`, `registry`, `core.ui` (XML parsing), `cli` dispatch.
- [ ] README contains a 60-second asciinema or terminal-recorded demo.
- [ ] `docs/ai-usage.md` shows a copy-paste recipe for Claude Code: "ask Claude to do X → Claude calls these commands → here's the trace".

## 8. Testing strategy

### Test pyramid

| Tier | % | Trigger | Scope |
|---|---|---|---|
| Unit | 70 | always (CI + local) | fixture-driven, no device |
| Integration | 25 | `EM_INTEGRATION=1` | real device, read-only verbs only |
| E2E | 5 | `EM_E2E=1` + `EM_ALLOW_COMMIT=1` | real device, has side effects, never in CI |

### Account safety rules

- **Douyin** is on a test account. Real send via `--commit` is allowed in E2E.
  - E2E comment test uses fixture text `[em-e2e <ts>] test`. After post, the test re-dumps and asserts comment is visible. Optional auto-delete is a v2 nicety.
- **Xiaohongshu** is on a personal account. `comment` verb has NO `--commit` flag in v1. The verb writes text into the input box and returns the would-be send button coordinates. The framework MUST NOT tap that button.
  - Integration test for xhs.comment asserts: input filled correctly, send button identified, and that the test then dismisses the compose modal.

### Real device pre-flight

Each integration / E2E test file begins with:

```python
import pytest
from mobilecli.adb.device import Device

@pytest.fixture(scope="session", autouse=True)
def verify_test_device():
    d = Device.from_env_or_default()
    assert d.serial == "EXAMPLE-SERIAL", f"unexpected device {d.serial}"
    assert d.is_online()
```

`comment --commit` additionally refuses to run unless `EM_ALLOW_COMMIT=1` is set in the environment.

## 9. Known gotchas (from UI tree research, 2026-05-21)

Encode these as documented retries / preconditions in Layer 2.

| App | Gotcha | Mitigation in Layer 2 |
|---|---|---|
| Douyin | Home autoplay video means `uiautomator dump` can fail with "could not get idle state". | `ui.dump()` retries up to 2x; if it still fails, taps the screen center once (to pause) and retries. |
| Douyin | Resource-ids are obfuscated 3-char strings (`2ei`, `gl1`) — change between releases. | Plugin selectors must prefer `content-desc` and class+position fallback, not resource-id. |
| Douyin | Foreground activity is `SplashActivity` even on home — not reliable for state detection. | `app.ensure_foreground("douyin")` checks for the bottom-nav element existence, not activity name. |
| Xiaohongshu | First launch routes to login wall; back + relaunch lands on guest home. | `app.launch("xiaohongshu")` runs the recovery sequence automatically on first failure. |
| Xiaohongshu | ADBKeyboard must be the active IME before `am broadcast ADB_INPUT_TEXT`; default IME silently drops it. | `ime.ensure_adbkeyboard()` is called at the top of any verb that types Chinese; restored on verb exit. |
| Both | Counts (likes/comments) live inside `content-desc` like `评论3809，按钮`. | `ui.parse_count(content_desc)` regex extractor in core.ui. |

Full selector inventories: `research/ui-trees/douyin/00-selectors.md` and `research/ui-trees/xiaohongshu/00-selectors.md`.

## 10. Open questions and follow-ups

These do not block v1 implementation; capture them for v2.

- Cloud-phone backend (Alicloud) as an alternative `Device` impl behind the same Layer 2 — the reference code already has this.
- Multi-device fan-out (`mobilecli --all <verb>`).
- Session/watch mode so Claude doesn't pay re-launch cost per command.
- Action recording → replay (for regression).
- `mobilecli douyin messages` and `mobilecli xiaohongshu messages` verbs.
- Image attachment in comments / posts.
- Captcha detection + escalation to human.

## 11. License & open-source posture

- MIT license.
- Repo name on GitHub: `everything-mobile` (or `mobilecli` if available).
- README front-loads: "no AI inside; designed to be driven by Claude Code, Codex, openclaw, etc."
- The reference code is **NOT** vendored in. Only general patterns informed the design.
