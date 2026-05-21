# everything-mobile

> AI-friendly CLI for driving Android phones — no AI inside.

**Status: alpha. Phase A primitives only. See `docs/superpowers/specs/2026-05-21-everything-mobile-design.md` for the v1 design.**

## Quickstart

```bash
pipx install -e .
mobilecli devices
mobilecli screenshot -o /tmp/x.png
```

---

## 准备工作：开启 ADB 调试（以红米 / Redmi 为例）

Redmi / Xiaomi（MIUI / HyperOS）需要做两件事：**开发者选项 + USB 调试 + USB 调试（安全设置）**。少了「安全设置」那个，本项目的 `tap` / `swipe` / `input` 都会被拒。

### 1. 解锁开发者选项

- 设置 → 我的设备 → 全部参数与信息 → 连续点击 **"OS 版本"**（HyperOS）或 **"MIUI 版本"**（旧版 MIUI）**7 次**
- 出现「您已处于开发者模式」提示即解锁

### 2. 打开 USB 调试

- 设置 → 更多设置 → **开发者选项**
- 打开 **「USB 调试」**
- 打开 **「USB 调试（安全设置）」**  ← 这一项很多教程不提，但这是 Redmi/MIUI 特有的开关，**不开就不能执行 `input tap` 等模拟操作**。打开时手机会弹窗要求登录小米账号
- 推荐打开 **「停用 adb 授权超时」**，否则隔几天要重新授权一次

### 3. 连接电脑，授权 RSA 指纹

```bash
adb devices
# 第一次会列出设备但 state 是 unauthorized
```

手机上会弹窗「允许调试」提示，勾选「始终允许」，确定。

```bash
adb devices
# 现在应该是: <serial>    device
```

### 4. 验证

```bash
mobilecli devices
# {"ok":true, "data":{"devices":[{"serial":"...","state":"device"}]}, ...}

mobilecli doctor
# 应全绿；如果 adbkeyboard_installed 是 warn，按下面安装

mobilecli screenshot -o /tmp/test.png
ls -la /tmp/test.png   # 几百 KB 的 PNG
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

## CLI 命令一览（Phase A 已实现）

| 命令 | 用途 | JSON 输出关键字段 |
|---|---|---|
| `mobilecli devices` | 列出连接的设备 | `data.devices[]` |
| `mobilecli screenshot [-o PATH]` | 截屏到 PNG | `data.path, size, width, height` |
| `mobilecli tap X Y` | 点击坐标 | `data.x, y, duration_ms` |
| `mobilecli swipe X1 Y1 X2 Y2 [--duration ms]` | 滑动 | `data.duration_ms` |
| `mobilecli type "文字"` | 输入文字（中文走 ADBKeyboard）| `data.chars, mode` |
| `mobilecli keyevent {back\|home\|enter\|...}` | 按键 | `data.code` |
| `mobilecli dump [-o PATH]` | uiautomator XML | `data.path, size` |
| `mobilecli launch <package>` | 启动 app | `data.package` |
| `mobilecli install <apk>` | 安装 APK | `data.result` |
| `mobilecli foreground` | 当前前台 app | `data.package, activity` |
| `mobilecli doctor` | 环境自检 | `data.checks[], summary` |

全局 flag：`--serial XXX`（多机时必填）、`--pretty`（JSON 缩进）、`--verbose`（stderr 调试）

---

## License

MIT.

**Phase A** ships primitives only. Humanization layer (anti-detection timing/jitter)、app plugins (douyin/xiaohongshu)、风控约束 + 完整免责声明等会在 Phase B/C/D 进来。完整设计见 `docs/superpowers/specs/2026-05-21-everything-mobile-design.md`。
