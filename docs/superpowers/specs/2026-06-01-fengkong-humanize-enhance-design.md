# 设计:全局风控增强(操作间高斯延迟 + 真曲线滑动 + 阅读行为)

- 日期:2026-06-01
- 状态:已与用户对齐(走"外科手术增强现有层 + 借 minitouch 技术"路线),待 spec 评审
- 仓库:`everything-mobile`(`mobilecli`)
- 背景:用户判断"直线滑动 + 无操作间停顿 + 无阅读行为"是封控主因(读 `input.py` 证实:`human_delay_s`/`bezier_swipe_points`/`read_pause_s` 都存在但**未真正接入**;swipe 实际发直线 `input swipe`)。Airtest 评估结论:不换框架,只借 minitouch 式连续手势技术。
- 真机事实(Pixel 10 Pro 探测):触摸设备 `/dev/input/event1`,type-B 多点(ABS_MT_SLOT max9 / TRACKING_ID),坐标范围 X∈[0,12799] Y∈[0,28559],屏 1080×2410 → 需运行时缩放。

## 1. 目标 / 范围

把已有但未接入的人类化能力**真正接进 `ctx.input.*`**,补三块封控短板。**不换框架、不动 verb 业务逻辑、不动 resource-id 找元素。**

| 增强 | 现状 | 目标 |
|---|---|---|
| 操作间随机延迟 | 无(verb 写死 `time.sleep`) | `ctx.input.*` 每个动作前高斯延迟 [2,10]s,可配 |
| 滑动轨迹 | 直线 `input swipe`,dur 0.6~1.2s | sendevent 连续曲线(沿现有贝塞尔点),dur 0.8~2.0s,失败回退直线 |
| 阅读行为 | `read_pause_s` 未接入 | 浏览类 verb 接入阅读停顿 + 偶发小幅来回滑动 |

## 2. 架构(组件 + 放置)

### 2.1 humanize.py:新增/调整采样器

```python
def pace_delay_s(lo: float = 2.0, hi: float = 10.0) -> float:
    """操作间延迟:截断高斯,均值=(lo+hi)/2,σ=(hi-lo)/4,clamp[lo,hi]。"""
    mu = (lo + hi) / 2
    sigma = (hi - lo) / 4
    return max(lo, min(hi, random.gauss(mu, sigma)))

def swipe_duration_s(lo: float = 0.8, hi: float = 2.0) -> float:
    return random.uniform(lo, hi)

def micro_wobble_swipe(center_y, screen_h) -> tuple[start, end]:
    """阅读时小幅来回:短距离上/下滑(看内容)。"""
```
`bezier_swipe_points`/`read_pause_s` 复用(已存在)。

### 2.2 pacing 接入点:`InputModule`(`plugin/ctx.py`)—— 唯一钩子

`ctx.input.*`(`tap_node`/`tap_xy`/`swipe`/`type_text`/`keyevent`)是所有 plugin 输入的唯一出口。在每个方法**动作前**插一次 `_pace()`:

```python
@dataclass
class InputModule:
    device: Device
    _first: bool = True   # 首个动作不等(verb 入口已自带导航 sleep)

    def _pace(self) -> None:
        if not _pacing_enabled():        # 读 env
            return
        if self._first:
            self._first = False
            return
        time.sleep(_hz.pace_delay_s(*_pace_bounds()))
```
每个方法体首行调 `self._pace()`。

- **配置(env,沿用 EM_ 前缀惯例)**:`EM_PACE=0` 关闭;`EM_PACE_MIN`/`EM_PACE_MAX` 调区间(默认 2/10)。`--raw` 模式下一并关闭(调试)。
- **⚠️ 延迟权衡**:publish 有 ~15+ 个 input 动作 → 默认 2~10s 会让 publish 多花 ~30–150s(单条可能 3–5 分钟)。这是风控正向的(慢=像人),且可调/可关。spec 显式记录,README 注明。

### 2.3 真曲线滑动:`core/input.py` + 设备探测

新增 `core/touch.py`:
```python
def probe_touch_device(device) -> dict | None:
    """getevent -lp 解析:返回 {event_node, x_max, y_max} 或 None(回退)。缓存到 ~/.everything-mobile/touch-<serial>.json。"""

def curved_swipe(device, points: list[tuple[int,int]], duration_s: float,
                 screen_wh: tuple[int,int]) -> dict:
    """把 points 缩放到设备坐标,拼成单条 sendevent 序列(down→逐点 move+SYN+sleep→up),
    一次 device.shell 下发;sleep 间隔 = duration/段数(±抖动)。探测失败返回 None。"""
```
type-B 序列(event 码:EV_ABS=3 ABS_MT_SLOT=47 ABS_MT_TRACKING_ID=57 ABS_MT_POSITION_X=53 ABS_MT_POSITION_Y=54;EV_KEY=1 BTN_TOUCH=330 BTN_TOOL_FINGER=325;EV_SYN=0):
```
sendevent N 3 47 0; sendevent N 3 57 <tid>; sendevent N 1 330 1; sendevent N 1 325 1;
sendevent N 3 53 <x0>; sendevent N 3 54 <y0>; sendevent N 0 0 0; sleep <dt>;
# 逐点: sendevent N 3 53 <xi>; sendevent N 3 54 <yi>; sendevent N 0 0 0; sleep <dt>;
sendevent N 3 57 4294967295; sendevent N 1 330 0; sendevent N 1 325 0; sendevent N 0 0 0
```
坐标缩放:`dev_x = round(screen_x * (x_max+1) / screen_w)`,Y 同理(范围/screen 从探测 + `wm size` 得)。

`swipe_humanized` 改:算 `bezier_swipe_points` → 试 `curved_swipe(...)`;成功用之;`None`(探测失败/异常)回退现有单条 `input swipe`(duration 改 `swipe_duration_s()`=0.8~2.0s)。**保证永不退化**。

### 2.4 阅读行为:`InputModule` 助手 + 浏览 verb 接入

```python
class InputModule:
    def reading_pause(self, text_length: int = 200) -> None:
        if _pacing_enabled():
            time.sleep(_hz.read_pause_s(text_length=text_length))
    def idle_browse(self, prob: float = 0.4) -> None:
        """偶发(prob)小幅来回滑动模拟看内容:小幅下滑 + 回滑。"""
```
浏览类 verb(douyin/xhs/kuaishou 的 `open`/`detail`/`search` 结果浏览)在读取后调 `ctx.input.reading_pause(...)`、偶尔 `idle_browse()`。**只接浏览语义点,不接 publish 这类填表流程**(那里加阅读停顿无意义)。

## 3. 不做(YAGNI)

- 不推 minitouch 二进制(sendevent 单命令已够;philosophy:不装额外 device 依赖)。
- 不做压力/多指手势(单指连续曲线足够)。
- 不重写 verb 业务逻辑;verb 里现有的功能性 `time.sleep`(等页面加载)保留——pacing 是**额外**的拟人停顿,不替换等待。
- 不动 tap 的 60% 抖动 / 时长(已够)。

## 4. 测试(TDD)

### 单测(`tests/unit/`)
- `test_humanize_pace.py`:`pace_delay_s` 落在 [2,10] 且分布近高斯(N 次采样均值≈6、min≥2、max≤10);`swipe_duration_s` ∈[0.8,2.0]。
- `test_touch_sendevent.py`:`curved_swipe` 用 mock device,断言下发的单条命令含 down/SYN/up 序列、坐标已按 x_max/y_max 缩放、move 点数=输入点数、sleep 段数正确;探测失败返回 None。
- `test_touch_probe.py`:`probe_touch_device` 解析一段 `getevent -lp` fixture → 正确抽 event_node/x_max/y_max;无触摸设备 → None。
- `test_pacing.py`:mock `time.sleep`,`EM_PACE=0` 不 sleep;默认开则每个动作(除首个)sleep 一次且参数在区间;`tap_node` 等都过 `_pace`。
- `test_input_swipe_fallback.py`:`swipe_humanized` 在 `curved_swipe` 返回 None 时回退 `input swipe` 且 duration∈[800,2000]ms。

### 集成(真机)
- 曲线滑动:`getevent -lp` 探测成功 → 一条 sendevent 命令能真实滚动 feed(对比直线);时长 0.8~2.0s。
- pacing:跑一个 verb 观察动作间隔变长;`EM_PACE=0` 恢复快速。
- 回退:临时令探测失败 → 仍能滑动(直线)。

## 5. 已知风险

1. **sendevent 设备相关**:event_node/坐标范围必须运行时探测,不同机型不同(本机 event1 / 12799×28559)。探测失败必须回退直线滑动——**永不因风控增强导致功能失效**。
2. **单命令长度**:35 点 × 4 sendevent ≈ 140 条 + sleep,拼一条 shell 可能很长;若超 adb 命令长度限制,降采样到 ~20 点或写临时 `.sh` push 执行。集成阶段定。
3. **publish 延迟**:默认 pacing 让 publish 慢到分钟级 → 可配/可关 + README 注明;调用方(营销智能体)可设 `EM_PACE_MIN/MAX` 调节。
4. **sleep 在 adb shell 内**:`toybox sleep` 支持小数(0.03)——本机 Android16 OK;老机型若不支持小数 sleep,降级为整数 ms 分组或 busybox。集成验。
5. 坐标缩放取整误差:命中区域足够大,忽略。

## 6. 实施阶段(单 plan,TDD)

1. **humanize 采样器**:`pace_delay_s`/`swipe_duration_s`/`micro_wobble_swipe` + 单测。
2. **pacing 接入**:`InputModule._pace` + env 配置 + 各方法接入 + 单测(mock sleep)。
3. **touch 探测**:`core/touch.probe_touch_device` + fixture 单测。
4. **曲线滑动**:`core/touch.curved_swipe` + 单测;`swipe_humanized` 接入 + 回退 + 单测。
5. **阅读行为**:`InputModule.reading_pause/idle_browse` + 浏览 verb 接入(douyin/xhs/kuaishou open/detail)。
6. **集成验**(真机):曲线滚动 / pacing / 回退;**publish + profile 回归**(确保 pacing 不破坏已验证流程,必要时集成测试设 `EM_PACE=0` 跑快)。
7. **文档**:README 风控层小节补 pacing/曲线/阅读 + env 配置;`docs/anti-risk-control.md` 标注实现已接入。

> 注:这是跨所有 app 的 Layer 2.5 增强,publish/profile 及现有 like/comment/reply 自动受益。
