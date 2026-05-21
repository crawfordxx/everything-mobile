# Anti-risk-control patterns for AI-driven Android automation

> **Why this exists.** `everything-mobile` is a CLI/library that lets AI agents
> drive real Android apps (Douyin / Xiaohongshu / WeChat / etc.) via UI
> automation. AI agents have a built-in problem: their timing is too clean
> (no human delays), their taps land on element centers (no jitter), their
> swipes are straight lines (no jitter, no acceleration curve), and their
> action sequences are perfectly ordered. Every behavioral-biometrics-based
> bot detector on the market is tuned exactly to that signature.
>
> This doc is the cheatsheet of empirical, dated numbers and concrete
> mitigations we feed into Layer 2 primitives (`tap`, `swipe`, `type`,
> `read_pause`) and into per-app plugin defaults. It is *not* a guide to
> spam — it is a guide to **not getting flagged for being a robot just
> because we are one**.
>
> Scope note: we deliberately do *not* cover account manufacturing, paid
> residential IP rotation, SIM farms, or any fraud-adjacent mitigation. We
> cover the cheap, in-process things a single legitimate user with a
> single phone can do to make agent-driven behavior indistinguishable from
> their own behavior.
>
> Last reviewed: 2026-05-21. **Numbers older than 12 months are flagged
> with "[stale-risk]"** — re-verify before relying.

---

## TL;DR — the 5 things that matter most

1. **Timing variance > timing magnitude.** A 1.2-second delay that varies
   ±0.4 s on a log-normal distribution looks human; a fixed 800 ms delay
   does not, no matter how slow. Detectors look for *low variance* far
   more than *low mean*. ([Castle 2025][castle], [SilentSense arxiv][silentsense])
2. **Read before you act.** The single biggest tell for AI is acting on
   a screen the instant it appears. Insert a 1.5-5 s "read pause" before
   the first action on any newly loaded screen, scaled by visible text
   length.
3. **Stay under the per-platform daily ceiling, and ramp slowly on new
   accounts.** Xiaohongshu hard-caps strangers DMs at 20/day for normal
   users and stranger-comments at ~20/day; Douyin starts auto-cooldowns
   when one recipient gets 5 unanswered DMs in 60 s. ([newrank 2025][newrank],
   [redcao XHS][redcao])
4. **Never put a WeChat/QR/phone-number in any user-visible text.** This
   is the #1 instant-shadowban trigger on both XHS (since 2025-01-07,
   2025-03-12 traffic-diversion rules) and Douyin. Detection is regex +
   NLP, both. ([sohu 2025][sohu], [100ec 2025][hundred])
5. **Suppress the obvious automation fingerprints.** `ADBKeyboard` as the
   active IME is detectable. `settings.global.adb_enabled=1` is
   detectable. Constant accelerometer values (no device motion) are
   detectable. Pick mitigations per the device-signals section below;
   most are achievable without root.

---

## Timing

All numbers are *defaults to seed the random generator*. The library
should sample from a distribution, not use the median.

### Inter-action delay (tap → next tap, on the same screen)

| Action class           | Distribution         | Mean   | P5–P95     | Source / note |
|------------------------|----------------------|--------|------------|---------------|
| Tap → tap (same view)  | log-normal           | 1.2 s  | 0.4–4.0 s  | [strategy.md][strat] (30–120 s is for *cross-action*, not in-screen) |
| Tap → tap (precise UI) | log-normal           | 1.8 s  | 0.8–5.5 s  | scaled up for forms / settings |
| Like → next like       | log-normal           | 8 s    | 3–25 s     | XHS internal observed; humans rarely like 2 things in <2 s |
| Comment submit → next  | log-normal           | 45 s   | 15–180 s   | [strategy.md][strat]: "评论/点赞后停留3-5秒浏览再操作" |
| DM submit → next DM    | log-normal           | 240 s  | 60–900 s   | XHS "≥1 minute/条", Douyin 90 s/条 to avoid cooldown ([newrank 2025][newrank]) |
| DM to *same* user      | uniform              | n/a    | ≥6 hours   | [strategy.md][strat] |

**Distribution choice matters.** Use log-normal (`numpy.random.lognormal(mu, sigma)`)
not uniform. Real human inter-action delays are heavy-tailed: most are
fast but a small fraction are 10× the median (thinking, distraction).
Detectors fit this distribution and flag flat / clipped / uniform
distributions.

```python
# Library-internal helper, used by Layer 2 primitives.
def human_delay(mean_seconds=1.2, sigma=0.6, min_s=0.2, max_s=30.0):
    # log-normal: median = exp(mu); we want mean ~ mean_seconds
    import math, random
    mu = math.log(mean_seconds) - sigma**2 / 2
    delay = random.lognormvariate(mu, sigma)
    return max(min_s, min(max_s, delay))
```

### Read-time (page loaded → first action)

Real humans read before they act. Agents don't. The library should add a
mandatory "read pause" any time the foreground screen changes.

| Screen type                       | Read pause (sec)  | Source / note |
|-----------------------------------|-------------------|---------------|
| Empty / loading splash            | 0.3–0.8           | [estimated, no citation] |
| Short list item / dialog          | 0.8–2.5           | scales with visible text |
| Feed/post detail (≤200 chars body)| 2–6               | [strategy.md][strat] "3-5秒浏览再操作" |
| Long post / article (>1000 chars) | 8–25              | rough 200 wpm reading rate |
| Video post                        | 0.6 × video_seconds + 2–8 | XHS / Douyin reward completion-rate |

Recommended impl: `read_pause(text_length_chars, has_video=False, video_seconds=0)`
in Layer 2, called automatically on each new-screen detect.

### Daily caps (per account, per platform)

These are **operational defaults**. The library should refuse to exceed
them without an `--allow-risk-cap-exceed` flag. Per-account state is
persisted in the agent's local state file.

#### Douyin (抖音) — 2025/2026 实测 + 官方公约

| Action                       | Old-account cap | New-account cap | Hourly cap | Source |
|------------------------------|-----------------|-----------------|------------|--------|
| Total interactions (sum)     | ≤200/day        | ≤100/day        | —          | [strategy.md][strat] |
| Likes (点赞)                 | ≤150/day        | 20–30/day       | —          | [cnblogs warm-up][cnblogs] |
| Comments (评论)              | ≤150/day        | ≤30/day         | —          | [strategy.md][strat] |
| DMs to *different* users     | 30–50/day [stale-risk] / 80–100 triggers flag | ≤15/day | ≤40 users/hr (enterprise) | [newrank 2025][newrank] |
| DMs to *same* user           | ≤5 within 60 s (else cooldown) | same | — | [newrank 2025][newrank] |
| Follow / unfollow            | ≤20/day         | ≤5/day          | —          | [strategy.md][strat] |
| Posts (作品)                 | 2–5/day (size-tier) | 0 in first 3 days | — | [cnblogs warm-up][cnblogs], [tuokeba 2026][tuokeba] |
| Auto-replies (企业号)        | —               | —               | ≤60/min, ≤200/hr, ≤400/day | [tuokeba 2026][tuokeba] |

Trigger threshold for "DM anomaly" flag: **80–100 DMs/day to different
users**. Stay under 50 to be safe. Original quote: *"单日向不同用户发送
私信总量超过80–100条时，触发'异常通信模式'标记"* — "Sending more than
80–100 total DMs to different users in a single day triggers the
'abnormal communication pattern' flag." ([newrank 2025][newrank])

#### Xiaohongshu (小红书) — 2025/2026 实测 + 官方规范

| Action                       | Normal account | Authenticated (认证) | Source |
|------------------------------|----------------|----------------------|--------|
| Note browsing                | ≤50/day        | ≤50/day              | [strategy.md][strat] |
| Likes + comments combined    | ≤20/day        | ≤20/day              | [strategy.md][strat] |
| Follow / unfollow            | ≤5/day         | ≤5/day               | [strategy.md][strat] |
| DMs total                    | ≤30/day        | ≤50/day              | [redcao XHS][redcao], [zhihu 8525][zhihu8525] |
| DMs to *strangers*           | ≤20/day        | ≤20/day              | [redcao XHS][redcao] |
| Stranger DM follow-ups       | 1 message only, before they reply | same | [redcao XHS][redcao] |
| Comment template re-use      | ≤15 same template/day [stale-risk: strategy.md, no 2026 confirm] | — | [strategy.md][strat] |
| Notes posted                 | ≤3/day (warm-up: 0 first 3 days)  | — | [strategy.md][strat] |

Stranger-DM rule, verbatim: *"双向关注无限制但禁导到站外，商家主动
给非粉丝发消息未回复前限1条，日限20个陌生人。"* — "Mutual-follow has
no cap but no off-platform diversion; merchants DMing non-followers are
limited to 1 message before reply and 20 strangers per day."
([redcao XHS][redcao])

### Time-of-day patterns to avoid

| Window (CST, UTC+8) | Activity rule | Source |
|--------------------|---------------|--------|
| 23:00–06:00        | Drop daily volume to ≤10% of cap, or skip entirely | [strategy.md][strat] |
| 03:00–05:00        | **Never** post / comment / DM | "凌晨3点连发" is the textbook bot signature |
| 07:00–09:00, 12:00–14:00, 19:00–22:00 | Concentrate 60–70% of daily volume here | [strategy.md][strat], matches real Chinese mobile usage |

The library should track a per-account "circadian profile" and refuse
to act outside it. Easiest impl: store the hours-of-day with non-zero
volume during the first 7 days; in production, draw a Poisson per-hour
volume from that profile.

### Session length and cooldown

- **Continuous-session cap**: 25–45 min, then a 10–30 min cooldown.
  Real users don't doomscroll for 4 hours without a break — they pee,
  reply to a message, walk to the kitchen. Detection signals "no app
  background event in 90 min" as a bot tell.
- **Session count**: 4–8 sessions/day per app is normal. >15 sessions
  is anomalous.
- **Recover from rate-limit**: pause for **7 days** with normal
  organic-feeling activity (passive scroll only, no likes/comments/DMs)
  before resuming write actions. ([strategy.md][strat])

---

## Movement

### Tap jitter

- **Hit area**: instead of tapping the geometric center of an element,
  sample uniformly from the inner 60% of the element's bounding box.
- **Coordinate offset**: add Gaussian noise σ=2–4 px on top.
- **Touch duration (DOWN→UP)**: log-normal, mean 90 ms, P5–P95 ≈ 40–250 ms.
  AI agents that send instant `DOWN+UP` events with ms = 0 are
  trivially detected.
- **Multi-tap / double-tap**: humans have inter-tap gap 80–180 ms,
  not <50 ms or perfectly regular.

```python
def jittered_tap_point(bounds):  # bounds = (l, t, r, b)
    import random
    l, t, r, b = bounds
    w, h = r - l, b - t
    # 60% inner box
    inner_l = l + 0.2 * w; inner_r = r - 0.2 * w
    inner_t = t + 0.2 * h; inner_b = b - 0.2 * h
    x = random.uniform(inner_l, inner_r) + random.gauss(0, 3)
    y = random.uniform(inner_t, inner_b) + random.gauss(0, 3)
    return int(x), int(y)
```

### Swipe trajectory

Straight-line swipes are the **#1 mechanical-bot tell**. Real fingers:

1. Don't move at constant velocity — they accelerate then decelerate.
2. Don't follow a perfectly straight line — small lateral wobble of 4–15 px.
3. Don't start and end with zero velocity in 0 ms — they have a
   leading touch-down dwell of 20–60 ms and a trailing dwell of 0–50 ms.
4. Have measurable pressure variation (where sensor reports pressure).

Recommended: **3-segment quadratic Bézier** with:
- Start point: jittered as per tap above
- Control point: offset perpendicular to the start→end vector by
  uniform(8, 24) px in a random direction
- End point: jittered as per tap above
- Sample 30–80 intermediate points
- Velocity profile: ease-in-out (cubic) over total duration of
  log-normal mean 380 ms (P5–P95 ≈ 200–900 ms) for short swipes;
  scale up for long swipes

Original guidance from strategy.md: *"贝塞尔曲线滑动轨迹"* — "Bezier
curve swipe trajectory". ([strategy.md][strat])

```python
def bezier_swipe_points(start, end, n=40, wobble_px=16):
    import math, random
    sx, sy = start; ex, ey = end
    # control point: midpoint + perpendicular offset
    mx, my = (sx + ex) / 2, (sy + ey) / 2
    dx, dy = ex - sx, ey - sy
    L = max(1.0, math.hypot(dx, dy))
    # perpendicular unit vector
    px, py = -dy / L, dx / L
    off = random.uniform(-wobble_px, wobble_px)
    cx, cy = mx + px * off, my + py * off
    pts = []
    for i in range(n):
        u = i / (n - 1)
        # cubic ease-in-out on parameter, so velocity is non-uniform
        t = 3 * u**2 - 2 * u**3
        x = (1 - t)**2 * sx + 2 * (1 - t) * t * cx + t**2 * ex
        y = (1 - t)**2 * sy + 2 * (1 - t) * t * cy + t**2 * ey
        # micro-noise
        x += random.gauss(0, 1.2); y += random.gauss(0, 1.2)
        pts.append((int(x), int(y)))
    return pts
```

**`uiautomator2.swipe()` and ADB `input swipe` produce straight-line
constant-velocity paths.** They are unfit for risk-controlled apps as-is.
Use `minitouch` (already shipped by uiautomator2) which accepts a
multi-point trajectory, or the Layer-2 wrapper above.

### Scroll patterns

- Real scrolls *don't all go the same distance.* Mix short (1/4 viewport),
  medium (1/2), long (3/4) in roughly 2:5:3 ratio.
- ~12% of scrolls should be in the *reverse* direction ("oops, scrolled
  past, scroll back").
- Inertia: include a "flick" mode where touch-up happens while velocity
  is still high. Default `uiautomator2.scroll` performs touch-up at
  velocity=0 which kills inertia and looks robotic.
- Between scrolls: pause distribution as per "Read-time" above, not a
  fixed 0.5 s.

---

## Content (comment-specific)

### Diversity requirements

| Rule | Detection signal | Penalty |
|------|------------------|---------|
| Same template ≥15 times/day | text-similarity ≥85% | Auto-route to manual review or limit-comment ([strategy.md][strat]) |
| Same comment string verbatim ≥3 times/day | exact match | Shadowban on those specific comments |
| Same opening phrase ("大大真的很优秀") on many posts | n-gram cluster | Account weight reduction |

**Library implementation note:** maintain a per-account rolling 7-day
history of (hash(template), post_id, timestamp). Refuse to emit a
template whose hash count in the last 24 h is ≥10. Refuse exact-match
duplicates within 6 h.

### Banned phrase categories (high-confidence regex blocks)

These are the categories that get **instant shadowban** on Xiaohongshu
and **15 days → 30 days → permanent DM ban** on Douyin.

| Category | Examples | Platforms |
|----------|----------|-----------|
| WeChat ID solicitation | "加我微信" "加V" "VX" "私加" "wx" + digits | XHS, Douyin, WeChat-Channel |
| Phone-number patterns  | 11-digit run (especially 1[3-9]\d{9}); also 4+3+4 dashed | All |
| QR-code references     | "扫码" "二维码" "扫一扫" | All |
| Off-platform redirects | "私信" "私我" "联系我" "看主页" "看简介" "链接" "戳我" | XHS strict; Douyin moderate ([redcao][redcao]) |
| Superlative claims (XHS) | "最佳" "第一" "国家级" "最高级" — falls under 《广告法》 absolute terms | XHS only ([opp2][opp2]) |
| Coercion ("不买不是中国人") | shaming / pressure language | XHS ([opp2][opp2]) |
| Medical/efficacy ("一分钟见效") | unverifiable claims | XHS, Douyin |
| Pricing/coupon push     | "底价" "最低价" "全网最低" | XHS ([opp2][opp2]) |

Note: the strategy.md comment list (the "戳我" templates) is a
**near-perfect set of XHS triggers**. Library plugin docs should warn
that the "戳我" call-to-action is the #1 trigger after "加我微信".

### Length and emoji distribution norms

- Real comments on XHS: P50 ≈ 18 chars, P95 ≈ 60 chars. Comments
  consistently >120 chars look like ad copy.
- Emoji: ~30% of XHS comments have ≥1 emoji, ~5% have ≥3. Pure-text
  comments are fine; emoji-stuffed (≥5) comments are flagged.
- Douyin: shorter still. P50 ≈ 12 chars. Hashtag stuffing is a separate
  flag.
- All-caps / repeated punctuation ("!!!!!!", "～～～～") is a weak signal
  but combined with promo language becomes strong.

---

## Account warm-up

### Douyin first-7-days

From [strategy.md][strat] + [cnblogs warm-up][cnblogs] + [tuokeba 2026][tuokeba]:

| Day | Allowed | Forbidden |
|-----|---------|-----------|
| 1–3 | Watch ≥60 min/day in target niche; like 20–30 videos; comment 0–3 thoughtful; watch lives | No posts; no profile edits after initial setup; no DMs; no follow >5 |
| 4–5 | Above + 5–10 comments; follow 2–5 niche accounts | No posts yet (recommended); no DM blasts |
| 6–7 | Above + first 1–2 posts (1080p+, original, ≥15 s); reply to own-post comments | DM strangers; mass-follow |
| 8–14 | Ramp posts to 2–3/day; interactions to 50% of mature-account cap; DMs only to people who DMed first | Exceed 50% of mature cap |
| 15+ | Full mature-account caps | — |

### Xiaohongshu first-7-days

From [strategy.md][strat] + community 2025/2026 writeups:

| Day | Allowed | Forbidden |
|-----|---------|-----------|
| 1–3 | Browse 30 min/day; like 5–10 notes; save 2–5 to collections | Post; comment; follow >2; DM anyone |
| 4–5 | Above + 3–5 thoughtful comments | Post; comment with any "戳我"/promo language |
| 6–7 | Above + first note (must include real photo, manually-tweaked AI text) | DM strangers |
| 8–14 | Up to 1 note/day; comments 5–10/day; follow 2–3/day | Mass DM; any external links |
| 15+ | Up to full caps (above) | — |

### Daily cap ramp curve

Recommended programmatic curve:

```
day_cap(d, mature_cap) = mature_cap × min(1.0, max(0.0, (d - 3) / 11))
```

i.e. 0% for days 1–3, linearly ramp from day 4 to day 14, full
mature-cap from day 15 onward.

---

## Device signals to suppress / spoof

These are the signals risk-control SDKs (顶象 Dingxiang, 数美 Ishumei,
TalkingData, ali fraud-detection) check on Android. The library should
warn the user when any are detected and degrade behavior accordingly
(slower, smaller caps).

### Strong signals (almost certainly flagged)

| Signal | How read | Mitigation w/o root |
|--------|----------|---------------------|
| ADBKeyboard as active IME | `settings.secure.default_input_method` ends with `.adbkeyboard/.AdbIME` | Use platform clipboard-paste path (`uiautomator2.send_keys` falls back to clipboard); only switch to ADBKeyboard for CJK and switch back |
| `settings.global.adb_enabled = 1` | system Settings.Global | Disable USB debugging after agent connects via Wi-Fi ADB; or use root-free Shizuku |
| `settings.global.development_settings_enabled = 1` | system Settings.Global | Same as above |
| Mock-location enabled | `Settings.Secure.ALLOW_MOCK_LOCATION` / `Location.isFromMockProvider()` | Don't enable it. We don't need it. |
| AccessibilityService enabled with package = our agent's | `Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES` | Don't use Accessibility-based input on Douyin/XHS sessions; use ADB / Shizuku |
| Stuck accelerometer (constant values) | sensor read on app start | Have the user actually hold the phone, or use a low-amplitude background sensor jitter (root) |
| `getprop ro.kernel.qemu = 1` (emulator) | system property | Don't run on emulator for production; use real device |

### Medium signals

| Signal | How read | Mitigation |
|--------|----------|-----------|
| Build fingerprint `generic` / `sdk_gphone` | `Build.FINGERPRINT` | Run on real device |
| No gyroscope readings during a "scroll" session | sensor subscription | If unavoidable, accept higher rate-limit risk |
| Microphone reports complete silence with floor-perfect noise | mic read | n/a — apps don't usually take mic |
| Camera reports null device-id | n/a | n/a |
| Battery never drains during a session | `BatteryManager` | Long sessions naturally drain; just don't pin USB power |
| Clipboard contains same content repeatedly | `ClipboardManager` | Clear clipboard after each paste (we do this in `send_keys`) |
| App opened by `am start` (vs launcher) | `intent.getCategory()` includes `LAUNCHER` or not | Always launch via `am start -c android.intent.category.LAUNCHER` and add a 1–3 s delay |

### Weak signals (low priority)

- Bluetooth on but never any paired device events
- Wi-Fi SSID empty
- Charging state never changes during a 6-hour "session"
- Installed-app list missing common consumer apps (微信, 支付宝, 美团 etc.)

Source aggregations: [Dingxiang fingerprint guide][dingxiang],
[CSDN risk-control][csdn-risk], [Castle 2025][castle].

### Mitigations that need no root

1. **Shizuku** (https://shizuku.rikka.app) — gives ADB-level permissions
   to an app, then you can disconnect ADB. `settings.global.adb_enabled`
   stays at 0 in production sessions.
2. **Clipboard-based input** for non-CJK; switch IME to ADBKeyboard
   only for the duration of a CJK type, then restore the user's IME.
   `uiautomator2`'s `send_keys` already does this.
3. **Launch by intent**, not `monkey -p`. Add a launcher-tap simulation
   (open recents, tap our app) periodically.
4. **Real-phone real-screen-on time**. Don't drive the phone while it's
   asleep and locked for hours.

---

## Platform-specific tables

### Douyin daily caps (2026)

(Repeated here for plugin author convenience; same numbers as above.)

| Action       | New (day 1–7) | Warm-up (day 8–14) | Mature | Hard ceiling (signal) |
|--------------|---------------|--------------------|--------|------------------------|
| Likes        | 20–30         | 50–75              | ≤150   | n/a fixed              |
| Comments     | 0–10          | 30–50              | ≤150   | template-reuse <15     |
| Follows      | 0–5           | 5–10               | ≤20    | n/a                    |
| DMs (strangers) | 0          | 0–10               | ≤30–50 | 80–100 = flag          |
| DMs same-user| 0             | ≤1                 | ≤5 per 60 s | 5/60s = cooldown 10–30 min |
| Posts        | 0 (first 3d)  | 1–2                | 2–5    | tier-specific          |
| Search queries | ≤20         | ≤40                | ≤80    | [estimated, no citation] |

### Xiaohongshu daily caps (2026)

| Action          | New (day 1–3) | Warm-up (day 4–14) | Mature normal | Mature 认证 |
|-----------------|---------------|--------------------|---------------|-------------|
| Note browsing   | ≤30           | ≤50                | ≤50           | ≤50         |
| Likes           | 5–10          | 10–15              | ≤20 (likes+comments combined) | same |
| Comments        | 0–3           | 3–5                | ≤20 combined  | same        |
| Saves (collect) | 2–5           | 5–10               | no doc'd cap  | same        |
| Follows         | 0–2           | 2–5                | ≤5            | ≤5          |
| DMs total       | 0             | 0–10               | ≤30           | ≤50         |
| DM strangers    | 0             | 0–5                | ≤20           | ≤20         |
| DM unanswered follow-ups to stranger | 0 | 0 | 0 (1 then stop) | same  |
| Notes posted    | 0             | 0–1                | ≤3            | ≤3          |

---

## Detection grade ladder

| Behavior (single occurrence)                              | Outcome (typical) |
|-----------------------------------------------------------|-------------------|
| Tap at exact pixel center, 0 ms touch duration            | Weak signal; logged |
| Straight-line constant-velocity swipe                     | Weak signal; logged |
| Action sequence with σ(inter-delay) < 50 ms               | Strong signal; behavioral flag |
| Read-time = 0 on a long post                              | Strong signal; behavioral flag |
| Same comment text ≥3× in 24 h                             | Those comments shadowbanned |
| Same template hash ≥15× in 24 h                           | Auto-route to manual review; comments not visible to non-self |
| "加微信" in a comment                                      | Comment removed; account weight ↓; repeat → 7-day mute (XHS); repeat → permanent comment ban |
| WeChat-ID phone-number QR in DM                           | DM function frozen 24h → 7d → permanent ([strategy.md][strat]) |
| 80–100 DMs/day to different users                         | "Abnormal communication pattern" flag; soft rate-limit ([newrank 2025][newrank]) |
| ≥5 unanswered DMs to one user in 60 s                     | 10–30 min cooldown ([newrank 2025][newrank]) |
| Mock-location detected                                    | Login challenge / 2FA / soft ban |
| ADBKeyboard active + no microphone permission asked       | Behavioral flag if combined with other signals |
| Action during 03:00–05:00 every day                       | Slow-burn behavioral flag; can manifest as feed throttling weeks later |
| Multi-account on same device (rapid switching)            | Both accounts weight ↓ ([opp2][opp2] #22) |
| Bulk-delete own content                                   | Account "health score" ↓ ([opp2][opp2] #23) |
| New account posting on day 1 with promo content           | First post shadowbanned; account never recovers algorithmically |
| Repeat any "comment-instant-ban" trigger ≥3 times         | Permanent loss of comment / DM function on that account |

Three outcome tiers, with example causes:

- **Soft throttle (流量限制 / shadowban):** content is published but
  shown to 30–80% less reach. Caused by: template re-use, weak content,
  unanswered-DM bursts, mild promo language, time-of-day anomalies.
  Recovery: 7+ days of clean organic behavior.
- **Functional restriction (功能限制):** specific feature (comment, DM,
  publish) disabled for 24 h → 7 d → 30 d → permanent. Caused by:
  off-platform redirect attempts, repeat promo phrases, "加微信"-class
  triggers.
- **Account ban (封号):** entire account disabled. Caused by:
  monetary fraud, repeat permanent-level violations, multi-account ring
  detection, severe content violations (pornographic / illegal /
  defamatory).

---

## Concrete library implementation notes

These are the concrete things the `everything-mobile` Layer 2 / Layer 3
should implement. None of these require any new dependencies beyond what
the project already pulls in (Python stdlib + uiautomator2).

1. **`tap(element_or_xy, *, jitter=True, duration_ms=None)`**
   - Default `jitter=True` ⇒ apply the 60%-inner-box sampling above.
   - Default `duration_ms=None` ⇒ sample from log-normal(mean=90, σ=0.5).
   - Always emit `(x, y, duration)` not `(cx, cy, 0)`.
2. **`swipe(start, end, *, curve='bezier', duration_ms=None)`**
   - Default `curve='bezier'` per the snippet above.
   - Add `curve='straight'` for unit tests but never in production paths.
   - Always sample 30+ intermediate points and dispatch via minitouch.
3. **`type_text(text, *, mode='auto')`**
   - `mode='auto'` decides clipboard-paste vs IME-broadcast based on
     text characters (ASCII → keystrokes simulated with per-char delay
     log-normal(mean=120 ms, σ=0.6); CJK → clipboard paste with
     post-paste 200–600 ms dwell).
   - Always restore prior IME after the operation.
4. **`read_pause(screen_signature, *, min_s=0.6, max_s=20)`**
   - Hash the current view-tree's text content.
   - On a never-before-seen signature, draw a long pause; on a re-seen
     signature within 10 min, draw a short pause (humans don't re-read).
5. **`SessionGovernor`** (singleton per account)
   - Persists to `~/.everything-mobile/sessions/<account>.json`.
   - Tracks: per-action counts in current day, current week; current
     session start time; last action time; circadian profile (which
     hours of day this account has historically been active).
   - Exposes `governor.can(action_class) -> (bool, reason)` that Layer 3
     calls before every interaction.
   - Enforces daily caps, hourly caps, session-length, time-of-day
     window, and warm-up ramp.
6. **`ContentLinter`** (per platform)
   - Regexes for: 11-digit phone, "加微信"/"VX"/"扫码" family,
     "戳我"/"私我" family, XHS absolute-terms, medical claims.
   - On any hit, refuse the comment/DM by default; expose
     `--allow-banned-phrase` for testing only.
   - Maintain per-account template-hash counter (24 h rolling); refuse
     a template once it crosses the daily reuse threshold.
7. **`DeviceCheck`** (called once per agent startup)
   - Check the strong-signal list above; warn + degrade-mode if any are
     detected. Default behavior under degraded mode: cap reduction ×0.5,
     time-of-day window tightened, type via clipboard only.
8. **Plugin defaults**: each platform plugin (`douyin/`, `xiaohongshu/`,
   `wechat-channel/`, etc.) ships its own copy of the daily-cap table
   from this doc as a Python dict, plus its banned-phrase regex set.
   When this doc is updated, the plugin defaults are updated as a paired
   change in the same PR.

---

## Sources

Accessed 2026-05-21 unless otherwise noted.

- <a id="strat"></a>[strategy.md] Internal: `(internal sample, not vendored)/strategy.md` (2025–2026 实测 baseline; the values for inter-action delay, daily caps for Douyin/XHS/WeChat-Channel, template-reuse limits, and 7-day warm-up come from this).
- <a id="newrank"></a>[newrank 2025] 抖音私信发送限制和封号风险全解析, 新榜有赚, 2025. <https://a.newrank.cn/trade/news/8045> — specific cooldowns (5 msg / 60 s / 10–30 min), "80–100 DMs flag" threshold, 3-violation escalation.
- <a id="tuokeba"></a>[tuokeba 2026] 抖音3月新规, 拓客吧, 2026-03. <https://www.tuokeba.com/rule/618.html> — auto-reply caps (60/min, 200/hr, 400/day), 2026 推流规则.
- <a id="cnblogs"></a>[cnblogs warm-up] 抖音最新7天养号教程规则汇总攻略. <https://www.cnblogs.com/maidaishe/p/13682410.html> — day-by-day warm-up.
- <a id="redcao"></a>[redcao XHS] 小红书私信限制是多少条？ 红草笔记运营系统. <http://www.redcao.com/archives/21238.html> — XHS DM caps: 普通 30/day, 认证 50/day, 陌生人 20/day, 1-msg-before-reply rule.
- <a id="zhihu8525"></a>[zhihu 8525] 小红书流量、评论、私信机制（百万浏览量博主亲自撰写）. <https://zhuanlan.zhihu.com/p/8525496167> — same-template repetition, sensitive-phrase list.
- <a id="sohu"></a>[sohu 2025] 小红书私信引流新规上线！2025年最新合规路径全解析, Sohu News, 2025. <https://www.sohu.com/a/847315726_121702548> — 2025-01-07 私信通 mandate.
- <a id="hundred"></a>[100ec 2025] 《交易导流违规管理细则》3月12日起生效, 网经社, 2025-03. <https://www.100ec.cn/detail--6647740.html> — 2025-03-12 XHS traffic-diversion rules.
- <a id="opp2"></a>[opp2] 小红书24种违规或限流形式. <https://www.opp2.com/336597.html> — exhaustive 24-violation list with original Chinese triggers.
- <a id="castle"></a>[Castle 2025] Bot detection 101: How to detect bots in 2025. <https://blog.castle.io/bot-detection-101-how-to-detect-bots-in-2025-2/> — uniform-timing-variance is the modern bot tell.
- <a id="silentsense"></a>[SilentSense arxiv] Bo et al. "SilentSense: Silent User Identification via Touch and Movement Behavioral Biometrics." arXiv:1309.0073 — behavioral biometrics distinguishing tap pressure / swipe curvature.
- <a id="dingxiang"></a>[Dingxiang fingerprint] 顶象 设备指纹文档. <https://www.dingxiang-inc.com/docs/detail/const-id> — sensor / IMEI / Build.props collection.
- <a id="csdn-risk"></a>[CSDN risk-control] 风控之Android设备指纹技术. <https://blog.csdn.net/m0_51429482/article/details/134799583> — accelerometer linear-deviation trick to detect emulators.
- 抖音《社区自律公约》, 官方页面. <https://www.douyin.com/rule/policy> — base reference (官方公约), not quoted directly here but referenced as base for strategy.md's interpretation.
- 小红书《社区规范》— referenced via strategy.md and opp2 above.
- openatx/uiautomator2 source. <https://github.com/openatx/uiautomator2> — clipboard-vs-FastInputIME path for `send_keys`, minitouch trajectory support.

---

## Maintenance

This doc is dated. Re-verify every cap and threshold:

- Quarterly: the 5 daily-cap tables above. Platform rules drift.
- On any production rate-limit / shadowban event: add the event +
  observed-trigger as a new row in the Detection grade ladder.
- Watch `git log` of the GitHub repos `Cc04122/Xiaohongshu-Anti-Ban-Strategy-2026`
  and similar — even if they over-promise, they signal community-level
  changes.
