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

Five layers, each only depends on the layer directly below it.

```
Layer 3 — App plugins              mobilecli.apps.douyin, mobilecli.apps.xiaohongshu
Layer 2.5 — Humanization & safety  humanize (timing/jitter/bezier), governor (caps), linter (banned phrases), device_check
Layer 2  — Generic primitives      screenshot, input (tap/swipe/type/keyevent), ui (dump+parse), app (launch/install/fg), ime
Layer 1  — ADB device backend      Device class: serial selection, shell exec, push/pull, timeouts, error mapping
Layer 0  — External (not ours)     adb binary, the Android device, the calling AI tool
```

Layer 2.5 is **not optional**. Layer 2 primitives apply humanization (jitter + delay) by default; bypassing requires `--raw` on the CLI (debugging only) or `ctx.raw_input` in plugin code (forbidden for production verbs). Rationale: an AI driver naturally produces clean, fast, pixel-perfect actions — exactly the signature behavioral-biometrics detectors are tuned for. The library must compensate.

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
| `--raw` | Disable humanization (no jitter, no delay, no governor, no linter). For debugging only — emits a warning on stderr. Requires `EM_ALLOW_RAW=1`. |
| `--account NAME` | Identifier for `SessionGovernor` persistence path (default `default`). Each account has its own daily-cap counter at `~/.everything-mobile/sessions/<account>.json`. |

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
                                            Read-only: tap home search affordance → type K → submit → parse result list → JSON.
                                            DOES NOT tap any result. Returns {results: [{index, cx, cy, title, author}, ...]}.
mobilecli douyin open --rank N             Tap the Nth search result from the current search-results screen. Lands on video detail.
mobilecli douyin detail                    Assume current screen is a video detail. Parse like/comment/share counts.
mobilecli douyin comment --text T [--commit]
                                            Open comment panel, fill text. WITHOUT --commit: leave as dry-run.
                                            WITH --commit: actually press send. Requires EM_ALLOW_COMMIT=1 env + governor budget.
mobilecli douyin back                      Press back. Recovery primitive used between iterations.
```

### Xiaohongshu verbs

```
mobilecli xiaohongshu launch               Launch. If first launch lands on login wall, press back + relaunch once.
mobilecli xiaohongshu search --keyword K [--limit N]
                                            Read-only: returns result list. DOES NOT tap any result.
mobilecli xiaohongshu open --rank N        Tap the Nth search result. Lands on note detail.
mobilecli xiaohongshu detail               Parse note detail (likes/comments/collects/title/author).
mobilecli xiaohongshu comment --text T     DRY-RUN ONLY in v1. No --commit flag. Send button is never pressed.
mobilecli xiaohongshu back                 Press back.
```

### Composition model (important)

The CLI is **stateless and orthogonal**: `search` only searches, `open` only navigates, `comment` only comments on the currently-foregrounded detail. There is **no `--all` or batch flag** — the AI driver loops in its own code. This keeps each command auditable, each tap risk-attributable to one input, and lets the governor pace operations:

```bash
# Search returns a list (no tap)
mobilecli xiaohongshu search --keyword 穿搭 --limit 10
# → {"data": {"results": [{"index": 1, "title": "...", ...}, ...]}}

# AI picks one, opens it (one tap)
mobilecli xiaohongshu open --rank 3

# Comment on the now-foreground detail (humanized + linted + governor-gated)
mobilecli xiaohongshu comment --text "学到了"

# Back to results to pick the next
mobilecli keyevent back

# Repeat. The SessionGovernor enforces inter-action delay + daily cap.
# When the cap is hit, `comment` returns RATE_LIMITED and the AI must stop.
```

For batch operations the AI orchestrates the loop. The library guarantees the per-action humanization but explicitly does NOT provide a "comment on all N results" verb — that would hide pacing from the AI and concentrate all the risk in one CLI call.

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
| `RATE_LIMITED` | governor refused (per-day / per-hour cap hit) | wait until reset; check `~/.everything-mobile/sessions/<account>.json` |
| `CONTENT_BANNED` | linter blocked the text (phone/微信/QR/etc.) | edit the text; or pass `--allow-banned-phrase` and `EM_ALLOW_RAW=1` (testing only) |
| `WARMUP_REQUIRED` | new account quota not yet ramped | wait until day-N of warm-up curve, or override via `--account-age-days N` |
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
│  │  ├─ input.py                tap/swipe/type/keyevent + tap_node helper (humanized by default)
│  │  ├─ ui.py                   dump + find_by_text/content_desc/resource_id/class
│  │  ├─ app.py                  launch/install/foreground/ensure_foreground
│  │  └─ ime.py                  ADBKeyboard setup
│  │
│  ├─ safety/                    Layer 2.5 — humanization & safety (NOT OPTIONAL)
│  │  ├─ __init__.py
│  │  ├─ humanize.py             log-normal delay, tap jitter (60% inner box),
│  │  │                          bezier swipe (30+ pts, ease-in-out + wobble),
│  │  │                          read_pause(screen_hash), per-char type delay
│  │  ├─ governor.py             SessionGovernor: per-account daily/hourly/session caps,
│  │  │                          warm-up ramp, persistence under ~/.everything-mobile/sessions/
│  │  ├─ linter.py               ContentLinter: regex blocks for phone/微信/VX/QR/扫码/戳我,
│  │  │                          per-platform template-reuse counter
│  │  └─ device_check.py         Detects ADBKeyboard-as-IME, adb_enabled=1, accessibility-svc.
│  │                              Reports degraded-mode signals on `doctor`.
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
- [ ] **Humanization layer is the default path.** `mobilecli tap X Y` (no flags) applies jitter + delay; `mobilecli --raw tap X Y` (with `EM_ALLOW_RAW=1`) bypasses. Unit tests verify both paths.
- [ ] **`SessionGovernor` enforces caps.** Per-account JSON at `~/.everything-mobile/sessions/<account>.json` tracks per-day / per-hour counts. Exceeding the cap returns `RATE_LIMITED`. Caps come from `docs/anti-risk-control.md` Douyin / XHS tables.
- [ ] **`ContentLinter` blocks instant-shadowban triggers.** Comment / DM verbs reject any text matching the regex set (`加微信`, `VX`, `扫码`, `戳我`, 11-digit phone, etc.). Override requires both `--allow-banned-phrase` and `EM_ALLOW_RAW=1`.
- [ ] **`doctor` reports humanization status** + device-fingerprint signals (`ADBKeyboard` IME, `adb_enabled`, accessibility services).
- [ ] README contains a 60-second asciinema or terminal-recorded demo.
- [ ] `docs/ai-usage.md` shows a copy-paste recipe for Claude Code: "ask Claude to do X → Claude calls these commands → here's the trace".
- [ ] `docs/anti-risk-control.md` is treated as a paired-change file: when caps change there, plugin defaults change in the same PR.

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

## 8.5. Humanization defaults (Layer 2.5)

Concrete defaults that Layer 2 primitives apply unless `--raw` is set. Sourced from `docs/anti-risk-control.md`.

### Timing

| Operation | Distribution | Notes |
|---|---|---|
| Inter-tap delay | log-normal(μ=1.2 s, σ=0.4 s), clamped [0.3, 8] | Per Castle 2025 — variance matters more than magnitude |
| Read-pause (new screen) | uniform(1.5, 5) s scaled by visible text length | First action on a never-before-seen screen-hash |
| Read-pause (revisit) | uniform(0.3, 1.2) s | Humans don't re-read content |
| Per-char type delay | log-normal(μ=120 ms, σ=0.6) | ASCII only; CJK uses clipboard paste + 200–600 ms post-paste dwell |
| Touch duration (tap) | log-normal(μ=90 ms, σ=0.5) | `input tap` is 0 ms — detectable; we always emit duration |
| Session length | 25–45 min then forced cooldown 8–20 min | Enforced by `SessionGovernor` |

### Movement

- **Tap jitter**: sample target within the inner 60% box of the element bounds (not the geometric center). Default `jitter=True` on every `tap`.
- **Swipe trajectory**: Bezier curve, 30+ intermediate points, ease-in-out velocity, 4–15 px lateral wobble at each segment, 80–200 ms leading dwell, 50–150 ms trailing dwell. `curve='straight'` only available in unit tests, never via CLI.
- **Scroll**: same Bezier model as swipe; the library never emits a single-segment scroll.

### Daily caps (seed values, configurable per account)

Sourced from `docs/anti-risk-control.md` §"Platform-specific tables". Plugins ship a copy in code; when the doc changes, both change in the same PR.

| Action | Douyin | Xiaohongshu |
|---|---|---|
| Comments to others | 100 / 50 (new) | 20 |
| DMs to strangers | 30–50 (new) / 80 (mature) | 20 |
| Total DMs/day | 100 | 30 |
| Follow / unfollow | 100 | 30 |
| Likes | 200 (mature) / 100 (new) | 100 |
| Hourly cap (any verb) | 60 | 30 |
| Same-template reuse (24 h) | 15 | 5 |

### Content lint (regex block list, raised as `CONTENT_BANNED`)

Default block-on-match regexes:

- `加.{0,4}微信|加.{0,4}V[X信]|VX[\\s:：]*\\w+`
- `扫.{0,3}码|扫.{0,3}二维码`
- `戳我|私我|滴滴我`
- `\\b1[3-9]\\d{9}\\b` (11-digit mainland mobile)
- `q[qQ][\\s:：]*\\d{5,}` (QQ number)
- `wx[\\s:：]*\\w+` (WeChat ID hint)

Plus per-platform extras living in plugin code.

### Device-fingerprint check (`doctor` reports)

| Signal | Detection | Mitigation |
|---|---|---|
| `ADBKeyboard` set as default IME at startup | `settings get secure default_input_method` | Switch to ADBKeyboard only during type, restore after |
| `settings.global.adb_enabled=1` | shell read | Can't hide; warn in degraded mode |
| Accessibility service of our package enabled | `settings.secure.enabled_accessibility_services` | Don't ship one for v1 |
| Constant accelerometer values | sensor read (not implemented v1) | Out of scope; this is why we target real devices |

Under degraded mode (any strong signal detected at startup): daily caps × 0.5, time-of-day window tightened to active hours only, type-by-clipboard only.

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

- **License:** MIT.
- **Repo name** on GitHub: `everything-mobile` (or `mobilecli` if available).
- **The reference code is NOT vendored in.** Only general patterns informed the design.

### README requirements (DoD)

The README is the project front door. It must contain, in this order:

1. **Disclaimer block at the very top** (English + 中文, both), shielding the maintainer:

   > **This project is for learning and security research only.** It is a generic Android automation library that demonstrates how AI agents can drive mobile apps. The maintainers do not endorse, recommend, or take responsibility for any use that violates the terms of service of any third-party platform (including but not limited to Douyin, Xiaohongshu, WeChat, TikTok). Users are solely responsible for their own actions, account safety, and compliance with applicable laws. Use of this project to spam, harass, mass-message, fake engagement, or evade platform anti-abuse measures is **explicitly out of scope** and unsupported. By using this software you accept all risk including but not limited to account suspension, rate-limiting, shadowban, and permanent device-level platform restrictions.
   >
   > **本项目仅用于学习与安全研究。** 这是一个通用的 Android 自动化库，演示 AI 代理如何驱动移动 App。维护者不鼓励、不推荐、不为任何违反第三方平台（包括但不限于抖音、小红书、微信、TikTok）服务条款的使用行为负责。使用者须独立承担行为、账号安全与法律合规责任。使用本项目用于刷量、骚扰、群发、伪造互动、规避平台反作弊机制等行为，**明确不在本项目支持范围内**。使用本软件即代表接受所有风险，包括但不限于账号封禁、限流、限评、设备级封锁。

2. **What this is** — one paragraph, plain language. AI-driven phone automation, no AI inside the lib.

3. **Quickstart** — `pipx install everything-mobile` + 3 example commands.

4. **CLI feature table** (the one the user requested) — required columns:

   | Command | Purpose | Example | JSON shape | Humanized? |
   |---|---|---|---|---|
   | `mobilecli devices` | list connected devices | `mobilecli devices` | `{ok, data: {devices: [...]}}` | — |
   | `mobilecli screenshot` | capture screen, write PNG | `mobilecli screenshot -o /tmp/x.png` | `{data: {path, size, width, height}}` | — |
   | `mobilecli tap X Y` | tap | `mobilecli tap 540 1200` | `{data: {x, y, duration_ms}}` | yes (jitter + duration) |
   | `mobilecli swipe ...` | gesture | `mobilecli swipe 540 1800 540 600` | `{data: {points: [...]}}` | yes (bezier + wobble) |
   | `mobilecli type "..."` | input text | `mobilecli type "美食"` | `{data: {chars}}` | yes (per-char delay) |
   | `mobilecli dump` | uiautomator XML | `mobilecli dump -o /tmp/x.xml` | `{data: {path, size}}` | — |
   | `mobilecli launch <pkg>` | open app | `mobilecli launch com.ss.android.ugc.aweme` | `{data: {foreground}}` | — |
   | `mobilecli douyin search` | structured search | `mobilecli douyin search --keyword 美食 --limit 5` | `{data: {keyword, results}}` | yes |
   | `mobilecli douyin comment` | post a comment | `mobilecli douyin comment --text "..." --commit` | `{data: {committed}}` | yes + linter |
   | `mobilecli xiaohongshu search` | structured search | `mobilecli xiaohongshu search --keyword 穿搭` | `{data: {keyword, results}}` | yes |
   | … all primitives + verbs … | | | | |

5. **Risk-control rules** — short prose explaining what `SessionGovernor` and `ContentLinter` do, with a link to `docs/anti-risk-control.md`. State that daily caps are enforced and `--raw` is debugging-only.

6. **Usage risks** — concrete list (account suspension / rate-limiting / shadowban / permanent device-level bans) so users understand what they are signing up for.

7. **What this is not** — explicit list: not a spam tool, not a follower-farm tool, not an engagement-faker, not a fraud framework. We refuse PRs for those features.

8. **Plugin authoring** — link to `docs/plugin-guide.md`.

9. **Contributing** — link.

10. **License** — MIT.

### Other open-source posture decisions

- README front-loads: "no AI inside; designed to be driven by Claude Code, Codex, openclaw, etc."
- No mention of any private brand ((internal) / (internal) / (internal sample) / internal model / (internal)) anywhere in the public repo.
- The reference code's marketing comment templates are **NOT** included as fixtures, examples, or defaults. They are explicitly the kind of payload `ContentLinter` exists to refuse.
- v1 ships with no example evil prompts. The example AI-usage doc demos benign verbs only (search results to JSON, read comment counts).
