# Changelog

## 1.1.1 — 2026-05-23

### Bug fixes (Xiaohongshu selector drift, observed against the current production app)
- Home-screen search affordance: try `iv_search` first, fall back to legacy `mSearchToolBarSearchBtn`, then `content-desc="搜索"`.
- Search input field: try `mSearchToolBarEt`, `et_search`, `search_edit`; final fallback finds the first `android.widget.EditText` on screen.
- Search result cards: tried `searchNoteCard` (legacy), `resultNoteContainer` (current `GlobalSearchActivity`); same fallback applied to `open --rank` and to the engage recovery oracle.
- Comment compose CTA: tap the bottom "说点什么..." bar (`inputCommentTV`) first, fall back to `noteCommentLayout`.
- Comment IME flow: for CJK text, pre-swap to ADBKeyboard *before* opening the compose overlay and only restore at end of verb. Previously the mid-flow `restore_ime` dismissed compose before the send button could be located.
- Engage recovery: bumped `_back_to_results` to 6 backs × 1.2 s. Each iteration now re-runs `search` from home if it lands stranded, so a single stuck overlay no longer wedges the rest of the run.

## 1.1.0 — 2026-05-23

### Features
- `mobilecli xiaohongshu like` — like the current note detail (dry-run by default; `--commit` + `EM_ALLOW_COMMIT=1` to actually tap). Daily cap = 100, enforced by `SessionGovernor`.
- `mobilecli xiaohongshu comment` — now honors the standard `--commit` gate (previously dry-run-only).
- `mobilecli xiaohongshu engage --keyword K [--limit N] [--like] [--comment-text T] [--sleep S] [--commit]` — compound verb that searches + iterates `open → detail → (like) → (comment) → back-to-results` on the top N hits. Each mutating step still respects `--commit` + governor + linter.

### Behavior changes
- Removed the spec §6 personal-account lock on Xiaohongshu mutating verbs. Safety now relies entirely on the same `--commit` + `EM_ALLOW_COMMIT=1` dual-gate that Douyin already uses, plus governor caps and content linting. README disclaimers updated accordingly.

### Tests
- Unit tests assert: XHS `comment.requires_commit_flag is True`, `like` verb present + gated, `engage` verb present + gated.

## 1.0.0 — 2026-05-21

First public release.

### Features
- 11 primitive commands: `devices`, `screenshot`, `tap`, `swipe`, `type`, `keyevent`, `dump`, `launch`, `install`, `foreground`, `doctor`
- 2 app plugins: `douyin` and `xiaohongshu`, each with `launch / search / open / detail / comment`
- Layer 2.5 humanization (NOT optional):
  - log-normal touch durations on tap/swipe
  - 60% inner-box jitter on `tap_node`; ±8 px jitter on `tap_xy`
  - bezier-shape swipe telemetry + endpoint ±4 px jitter + randomized [600,1200] ms duration
  - per-char log-normal delay for ASCII typing; ADBKeyboard + post-paste dwell for CJK
- `SessionGovernor` with per-account JSON persistence at `~/.everything-mobile/sessions/<account>.json` + per-day caps
- `ContentLinter` with banned-phrase regex (加微信 / VX / 扫码 / 戳我 / 11-digit phone / QQ / wx-id)
- `DeviceCheck` reporting fingerprint signals (`adb_enabled`, ADBKeyboard as default IME) via `doctor`
- External plugin discovery via the `mobilecli.apps` entry_points group
- Stable JSON envelope: `{ok, command, device, elapsed_ms, data | error}`; 12 typed `ErrorCode`s including `RATE_LIMITED`, `CONTENT_BANNED`, `COMMIT_REFUSED`
- `--raw` opt-out gated by `EM_ALLOW_RAW=1`; `--commit` on state-mutating verbs gated by `EM_ALLOW_COMMIT=1`
- 52 unit tests + 10 integration tests (real device); ruff + mypy strict clean

### Anti-scope (intentional)
- No batch / `--all` verbs. AI orchestrates loops.
- No WeChat / 微信 plugin.
- No cloud-phone backend.
- No spam helpers, follower farms, or engagement fakers.
- Xiaohongshu `comment` is dry-run only — no `--commit` flag exists in v1.

### Docs
- README with Redmi/MIUI ADB setup walkthrough + full CLI table + risk-control rules + usage risks + anti-scope + bilingual disclaimer
- `docs/ai-usage.md` — driving guide for Claude Code / Codex / openclaw
- `docs/plugin-guide.md` — authoring external `mobilecli.apps` plugins
- `docs/anti-risk-control.md` — empirical 2025-2026 timing/cap/lint baseline
- `CONTRIBUTING.md` — PR requirements + safety guarantees
