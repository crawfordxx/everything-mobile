# Driving everything-mobile from Claude Code / Codex / openclaw

This doc is for an AI agent invoking `mobilecli`. Read it once, then drive.

## Mental model

- `mobilecli` is stateless. Every invocation is independent.
- Output is **always JSON** to stdout. Parse it. Don't grep prose.
- Screenshots and dumps are written to disk; the JSON returns the path. Read the PNG/XML with your built-in tools — don't pipe binary into stdout.
- The library has **no AI**. You are the AI. The library handles tap/swipe/dump/parse and the safety layers; you handle decisions.

## Envelope

Success:
```json
{"ok": true, "command": "<name>", "device": "<serial>", "elapsed_ms": <int>, "data": {...}}
```

Failure:
```json
{"ok": false, "command": "<name>", "device": "<serial>", "elapsed_ms": <int>,
 "error": {"code": "<CODE>", "message": "...", "hint": "..."}}
```

`hint` is for you. It tells you the next command to run to recover.

## Error code → recovery

| Code | What to do |
|---|---|
| `NO_DEVICE` | Run `adb devices`. Ask the human to plug in. |
| `MULTIPLE_DEVICES` | Pick one with `--serial XXX` or set `EM_SERIAL`. |
| `ADB_TIMEOUT` | Device is hung. One retry, then ask the human. |
| `APP_NOT_INSTALLED` | Stop. Don't pretend to install via apkpure. Tell the human. |
| `APP_NOT_FOREGROUND` | Run `<app> launch` first. |
| `ELEMENT_NOT_FOUND` | Run `mobilecli dump` to see current state. UI may have moved. |
| `IME_NOT_SET` | Run `mobilecli doctor` — it will report if ADBKeyboard isn't installed. |
| `COMMIT_REFUSED` | You tried `--commit` without `EM_ALLOW_COMMIT=1`. Don't fight the gate — tell the human. |
| `RATE_LIMITED` | Daily cap hit for `--account`. Stop the loop. Don't switch accounts to evade. |
| `CONTENT_BANNED` | Your comment contains 加微信 / phone / 戳我 / etc. Rewrite without contact info. |
| `WARMUP_REQUIRED` | Account is new; respect the warm-up curve. |
| `UNKNOWN` | Re-run with `--verbose` to see stderr. |

## Example session

```bash
# 1. Verify device
mobilecli devices
# → {"data": {"devices": [{"serial": "5A170...", "state": "device"}]}}

# 2. Look at the screen (Claude/Codex read this PNG with native vision)
mobilecli screenshot -o /tmp/screen.png

# 3. Drive Douyin search
mobilecli douyin launch
mobilecli douyin search --keyword 美食 --limit 5
# → data.results = [{index, cx, cy, bounds}, ...]
# You pick one — say index 3
mobilecli douyin open --rank 3
mobilecli douyin detail
# → {likes, comments, shares, collects}
```

## Composition: no batch verbs

There is no `--all` or batch flag. Loop in your driver code so the `SessionGovernor` can pace and so each tap is one auditable input:

```bash
# Pseudocode for an AI driver
results=$(mobilecli xiaohongshu search --keyword 穿搭 --limit 10 \
          | jq -r '.data.results[].index')
for i in $results; do
    mobilecli xiaohongshu open --rank "$i"
    mobilecli xiaohongshu detail | jq .
    mobilecli xiaohongshu back
done
```

If `RATE_LIMITED` comes back, **stop the loop**. Do not switch accounts or rotate identity to keep going — that's the spam path this library refuses to support.

## Comment safety

`mobilecli douyin comment --text "..."` is **dry-run by default**. It will:
1. Lint the text (refuses 加微信 / phone / 戳我 / etc.)
2. Check the governor's per-day cap
3. Open the compose box, type the text, find the send button
4. Press back without sending
5. Return `{dry_run: true, committed: false, send_button_cx, send_button_cy}`

To actually send, you need **both** `--commit` and `EM_ALLOW_COMMIT=1`. Don't set those without explicit human authorization.

`mobilecli xiaohongshu comment` and `mobilecli xiaohongshu like` follow the same dual-gate (`--commit` + `EM_ALLOW_COMMIT=1`). `mobilecli xiaohongshu engage --keyword K [--like] [--comment-text T]` is a compound verb that searches and then iterates `open → detail → (like) → (comment) → back-to-results` on the top N hits; the same dual-gate applies. Daily caps are enforced per-iteration. Default = dry-run; do NOT pass `--commit` unless a human explicitly authorized this run.

## What you should never do

- Don't loop without checking for `RATE_LIMITED` between iterations
- Don't strip Chinese punctuation from text to evade the linter
- Don't run `--raw` unless the human asked you to debug something
- Don't propose `--account other-account` after hitting a cap on the first one
- Don't `mobilecli install` an APK the human didn't hand you

If the human's intent sounds like "make this account look more active than it is" — stop and push back. That's not what this tool is for.
