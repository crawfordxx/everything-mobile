# everything-mobile

> AI-friendly CLI for driving Android phones — no AI inside.

`mobilecli` is a Python CLI that lets external AI agents (Claude Code, Codex CLI, openclaw, etc.) drive a physical Android phone. Every command is JSON-in / JSON-out and stateless; the AI reads screenshots / XML dumps the CLI writes to disk and decides what to do next.

There is **no AI inside this library**. The intelligence lives in whatever tool is invoking `mobilecli`.

---

## ⚠️ Disclaimer / 免责声明

> **This project is for learning and security research only.** It is a generic Android automation library that demonstrates how AI agents can drive mobile apps. The maintainers do not endorse, recommend, or take responsibility for any use that violates the terms of service of any third-party platform (including but not limited to Douyin / 抖音, Xiaohongshu / 小红书, WeChat / 微信, TikTok). Users are solely responsible for their own actions, account safety, and compliance with applicable laws. Using this project to spam, harass, mass-message, fake engagement, or evade platform anti-abuse measures is **explicitly out of scope** and unsupported. By using this software you accept all risk including but not limited to account suspension, rate-limiting, shadowban, and permanent device-level platform restrictions.
>
> **本项目仅用于学习与安全研究。** 这是一个通用的 Android 自动化库，演示 AI 代理如何驱动移动 App。维护者不鼓励、不推荐、不为任何违反第三方平台（包括但不限于抖音、小红书、微信、TikTok）服务条款的使用行为负责。使用者须独立承担行为、账号安全与法律合规责任。使用本项目用于刷量、骚扰、群发、伪造互动、规避平台反作弊机制等行为，**明确不在本项目支持范围内**。使用本软件即代表接受所有风险，包括但不限于账号封禁、限流、限评、设备级封锁。

---

## Quickstart

```bash
pipx install -e .
mobilecli devices
mobilecli doctor
mobilecli screenshot -o /tmp/x.png
```

For the **first-time Redmi/MIUI ADB setup**, see the section below before anything else works.

---

## 准备工作：开启 ADB 调试（以红米 / Redmi 为例）

Redmi / Xiaomi（MIUI / HyperOS）需要做三件事：**开发者选项 + USB 调试 + USB 调试（安全设置）**。少了「安全设置」那个，本项目的 `tap` / `swipe` / `input` 都会被拒。

### 1. 解锁开发者选项

- 设置 → 我的设备 → 全部参数与信息 → 连续点击 **"OS 版本"**（HyperOS）或 **"MIUI 版本"**（旧版 MIUI）**7 次**
- 出现「您已处于开发者模式」提示即解锁

### 2. 打开 USB 调试

- 设置 → 更多设置 → **开发者选项**
- 打开 **「USB 调试」**
- 打开 **「USB 调试（安全设置）」** ← 这一项很多教程不提，但这是 Redmi/MIUI 特有的开关，**不开就不能执行 `input tap` 等模拟操作**。打开时手机会弹窗要求登录小米账号
- 推荐打开 **「停用 adb 授权超时」**，否则隔几天要重新授权一次

### 3. 连接电脑、授权 RSA 指纹

```bash
adb devices
# 第一次会列出设备但 state 是 unauthorized
```

手机上会弹窗「允许调试」提示，勾选「始终允许」，确定。

```bash
adb devices
# 现在: <serial>    device
```

### 4. 验证

```bash
mobilecli devices
mobilecli doctor
mobilecli screenshot -o /tmp/test.png
ls -la /tmp/test.png
```

### 5. （可选但推荐）安装 ADBKeyboard 以支持中文输入

ADB 自带的 `input text` 不支持中文。装一个开源 IME 让 `mobilecli type "学到了"` 能用：

```bash
# 从 https://github.com/senzhk/ADBKeyBoard 下载 ADBKeyboard.apk
adb install ADBKeyboard.apk
adb shell ime enable com.android.adbkeyboard/.AdbIME
# mobilecli 在需要中文时会自动切到这个 IME，结束后切回原 IME
```

### 常见问题

- **`unauthorized`**：手机上没勾「始终允许」，重新插拔 USB 看弹窗
- **`offline`**：换一根带数据的 USB 线（充电专用线只供电不通信）
- **`tap` 无效但没报错**：「USB 调试（安全设置）」没开
- **连不上**：USB 模式选成「仅充电」了，改成 **「文件传输 (MTP)」** 或 **「PTP」**
- **MIUI 14+ 上 `pm list packages` 卡住**：开发者选项里关掉「MIUI 优化」，重启手机

---

## CLI 命令全表

### 通用原语（Layer 2）

| 命令 | 用途 | JSON `data` 关键字段 | 人类化默认开 |
|---|---|---|---|
| `mobilecli devices` | 列出连接的设备 | `devices[]` | — |
| `mobilecli screenshot [-o PATH]` | 截屏到 PNG | `path, size, width, height` | — |
| `mobilecli tap X Y` | 点击坐标 | `x, y, duration_ms` | ✓ jitter + 时长随机 |
| `mobilecli swipe X1 Y1 X2 Y2 [--duration ms]` | 滑动 | `x1, y1, x2, y2, duration_ms, points` | ✓ 端点 jitter + 时长随机 + bezier 遥测点 |
| `mobilecli type "文字"` | 输入文字 | `chars, mode` | ✓ 每字符 log-normal 间隔 + ADBKeyboard for CJK |
| `mobilecli keyevent {back\|home\|enter\|recent\|menu\|...}` | 按键 | `code` | — |
| `mobilecli dump [-o PATH]` | uiautomator XML | `path, size` | — |
| `mobilecli launch <package>` | 启动 app | `package` | — |
| `mobilecli install <apk>` | 安装 APK | `apk, result` | — |
| `mobilecli foreground` | 当前前台 app | `package, activity` | — |
| `mobilecli doctor` | 环境自检 + 风控信号 | `checks[], summary` | — |

### App 子命令（Layer 3）

| 命令 | 用途 | 备注 |
|---|---|---|
| `mobilecli douyin launch` | 启动抖音 | |
| `mobilecli douyin search --keyword K [--limit N]` | 搜索视频 | 返回结果列表，**不自动点开** |
| `mobilecli douyin open --rank N` | 点开第 N 个搜索结果 | |
| `mobilecli douyin detail` | 抓当前视频互动数据 | |
| `mobilecli douyin comment --text T [--commit]` | 在当前视频下评论 | 默认 dry-run；`--commit` 需 `EM_ALLOW_COMMIT=1` |
| `mobilecli xiaohongshu launch` | 启动小红书 | |
| `mobilecli xiaohongshu search --keyword K [--limit N]` | 搜索笔记 | 返回结果列表 |
| `mobilecli xiaohongshu open --rank N` | 点开第 N 个结果 | |
| `mobilecli xiaohongshu detail` | 抓笔记互动数据 | |
| `mobilecli xiaohongshu comment --text T` | 在当前笔记下评论 | **v1 永远 dry-run，不真发**（无 `--commit` flag）|

### 全局 flag

| Flag | 含义 |
|---|---|
| `--serial SERIAL` | 指定设备（多机时必填，单机时可省，读 `EM_SERIAL` 兜底） |
| `--pretty` | JSON 缩进打印 |
| `--verbose` | stderr 调试日志 |
| `--timeout SEC` | 单条命令超时（默认 30s） |
| `--raw` | 关闭人类化（仅调试用；需 `EM_ALLOW_RAW=1`）|
| `--account NAME` | SessionGovernor 账号标识（默认 `default`） |

---

## 人类化与风控约束（Layer 2.5）

`mobilecli` 默认就给所有 `tap` / `swipe` / `type` 加上：

- **时序方差**：`tap` 触屏时长 log-normal(μ=90ms, σ=0.5)，不是 `input tap` 那种 duration=0 的指纹
- **坐标抖动**：`tap_humanized` 在元素 bounds 内框 60% 区域随机采样；按坐标点的话 ±8 px 抖动
- **滑动**：bezier 端点 ±4 px + 时长 [600,1200] ms 随机化
- **打字**：ASCII 每字符 log-normal(μ=120ms, σ=0.6) 间隔
- **`SessionGovernor`**：每个 `--account` 的每日动作计数持久化到 `~/.everything-mobile/sessions/<account>.json`；超 cap → `RATE_LIMITED` envelope
- **`ContentLinter`**：自动拦截「加微信 / VX / 扫码 / 戳我 / 11 位手机号 / QQ / wx-id」等明显引流文案 → `CONTENT_BANNED` envelope

完整时序参数、风控研究与平台 cap 表见 [`docs/anti-risk-control.md`](docs/anti-risk-control.md)。

**这一层不能关。** `--raw` 仅为调试存在，需 `EM_ALLOW_RAW=1` 环境变量，且会在 stderr 警告。

---

## 使用风险（一定要知道）

把这个工具当成你账号的代理人时，可能发生：

- **账号限流 / 限评 / 限关注**（平台的「请稍后再试」/ 互动数据冻结）
- **影子封禁（shadowban）**：内容不再分发但你看不到提示
- **临时功能限制 24h → 7 天 → 30 天 → 永久**（多平台累进逻辑一致）
- **整机风控**：同一设备下的所有同平台账号一起被关注
- **法律 / 合规风险**：在某些场景被认定为「未经授权的自动化访问」

平台规则随时变。`docs/anti-risk-control.md` 的数据是 2025–2026 实测 + 官方公约整理的，但请把它当作下限——不是「这样发就一定安全」。

---

## What this is NOT / 不是什么

这些用例**不在本项目支持范围内**，对应 PR 会被关闭：

- ❌ 群发私信 / 群发评论 / 群发关注的「营销工具」
- ❌ 刷赞 / 刷粉 / 刷阅读 / 刷互动 的造数工具
- ❌ 自动批量注册账号 / 养号工具链 / 接码平台对接
- ❌ 绕过人机验证 / 滑块 / 拼图的工具
- ❌ 仿冒登录态 / 撞库 / 凭据填充
- ❌ 任何旨在欺骗平台检测、骚扰其他用户、伪造统计的功能

如果你的场景听起来像上面任何一条 — 请别提 issue，也别开 PR。

---

## 给 AI 看的使用指南

如果你是 Claude Code / Codex / openclaw 这类 AI 驱动者，请看 [`docs/ai-usage.md`](docs/ai-usage.md)：里面有完整的调用范式 + 批量场景示例 + 错误码处理。

---

## 写你自己的 app plugin

`mobilecli` 用 `entry_points` 机制支持外部插件。`pip install mobilecli-tiktok` 之类的包可以自动注册到 `mobilecli tiktok ...` 子命令。

完整指南：[`docs/plugin-guide.md`](docs/plugin-guide.md)。

---

## Contributing

PR 欢迎，但务必先看 [`CONTRIBUTING.md`](CONTRIBUTING.md)。新 verb 必须配 fixture 单测 + 真机集成测试。匿名 PR 会被关闭。

---

## License

MIT.
