# 小红书 publish + profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `mobilecli` 加跨端发布地基(`ctx.media.push_to_gallery` + 区域截图裁剪)、小红书 `profile`(登录态+头像/昵称)与 `publish`(图文/视频:标题/正文/话题/封面/笔记内容声明)。

**Architecture:** 沿用现有分层——纯逻辑(判型/解析/排序)抽成模块级函数走单测(fixture);设备编排放 `apps/xiaohongshu.py` verb,走 `ExecContext` 安全层;变更动作(publish)双闸 dry-run/`--commit`+governor+linter,只读动作(profile)无闸。selector 事实源:`research/ui-trees/xiaohongshu/00-selectors-publish.md` + `00-selectors.md`「我/profile」节。

**Tech Stack:** Python 3.10+, pytest, Pillow(头像裁剪), adb(uiautomator dump / screencap / input / am broadcast / content query)。

**先后:** Phase 0 地基 → Phase 1 profile(只读、快、先验证)→ Phase 2 publish。

---

## File Structure

- `src/mobilecli/envelope.py` — 加 3 个 ErrorCode(`INVALID_ARG`/`PERMISSION_REQUIRED`/`MEDIA_NOT_INDEXED`)
- `pyproject.toml` — 加 `pillow` 运行时依赖
- `src/mobilecli/core/screenshot.py` — 加 `capture_region`(全屏截图 + Pillow 裁剪)
- `src/mobilecli/core/media.py` — **新建**,`push_to_gallery`(push + touch mtime + 媒体扫描 + MediaStore 回查)的纯/半纯逻辑
- `src/mobilecli/plugin/ctx.py` — 加 `MediaModule`(挂 `ctx.media`)+ `UiModule.screenshot_region`
- `src/mobilecli/apps/xiaohongshu.py` — 加 `_parse_profile`、`profile` verb;`_classify_media`、`_parse_tags`、`_order_media_for_cover`、`publish` verb;caps 加 `publish:3`
- `tests/fixtures/xhs-profile.xml` — profile 页 fixture(从 recon 复制)
- `tests/unit/test_media_push.py`、`test_xhs_profile.py`、`test_xhs_publish_args.py` — 新建单测
- `README.md` — CLI 表加 `xiaohongshu profile` / `publish`

---

## Phase 0 — 地基

### Task 1: 新增 ErrorCode

**Files:**
- Modify: `src/mobilecli/envelope.py:18-30`
- Test: `tests/unit/test_envelope.py`

- [ ] **Step 1: 写失败测试**

在 `tests/unit/test_envelope.py` 末尾加:

```python
def test_new_error_codes_exist():
    from mobilecli.envelope import ErrorCode
    assert ErrorCode.INVALID_ARG.value == "INVALID_ARG"
    assert ErrorCode.PERMISSION_REQUIRED.value == "PERMISSION_REQUIRED"
    assert ErrorCode.MEDIA_NOT_INDEXED.value == "MEDIA_NOT_INDEXED"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/test_envelope.py::test_new_error_codes_exist -v`
Expected: FAIL — `AttributeError: INVALID_ARG`

- [ ] **Step 3: 加枚举**

`src/mobilecli/envelope.py`,在 `WARMUP_REQUIRED = "WARMUP_REQUIRED"` 后、`UNKNOWN` 前插入:

```python
    INVALID_ARG = "INVALID_ARG"
    PERMISSION_REQUIRED = "PERMISSION_REQUIRED"
    MEDIA_NOT_INDEXED = "MEDIA_NOT_INDEXED"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/unit/test_envelope.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mobilecli/envelope.py tests/unit/test_envelope.py
git commit -m "feat(envelope): add INVALID_ARG/PERMISSION_REQUIRED/MEDIA_NOT_INDEXED codes"
```

### Task 2: 加 Pillow 依赖

**Files:**
- Modify: `pyproject.toml:31`(`dependencies = []`)

- [ ] **Step 1: 改依赖**

把 `pyproject.toml` 的 `dependencies = []` 改为:

```toml
dependencies = [
    "pillow>=10.0",
]
```

- [ ] **Step 2: 安装**

Run: `pip install -e .`
Expected: 成功安装 pillow

- [ ] **Step 3: 验证可导入**

Run: `python -c "from PIL import Image; print(Image.__version__)"`
Expected: 打印版本号

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: add pillow runtime dependency (avatar crop)"
```

### Task 3: core.screenshot.capture_region + UiModule.screenshot_region

**Files:**
- Modify: `src/mobilecli/core/screenshot.py`
- Modify: `src/mobilecli/plugin/ctx.py`(`UiModule`)
- Test: `tests/unit/test_screenshot_region.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/test_screenshot_region.py`:

```python
"""capture_region: 裁剪指定 bounds。"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from mobilecli.core import screenshot


class _FakeDevice:
    """exec_out 返回一张 100x200 的纯色 PNG。"""

    def exec_out(self, argv, timeout_s=30):
        img = Image.new("RGB", (100, 200), (10, 20, 30))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


def test_capture_region_crops_bounds(tmp_path):
    out = tmp_path / "crop.png"
    res = screenshot.capture_region(_FakeDevice(), (10, 20, 60, 120), str(out))
    assert res["width"] == 50
    assert res["height"] == 100
    with Image.open(out) as im:
        assert im.size == (50, 100)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/test_screenshot_region.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'capture_region'`

- [ ] **Step 3: 实现 capture_region**

`src/mobilecli/core/screenshot.py` 末尾加(并在文件顶 import 区加 `import io`):

```python
def capture_region(
    device: Device,
    bounds: tuple[int, int, int, int],
    output_path: str | None = None,
) -> dict[str, Any]:
    """Screencap full screen, crop to `bounds` (x1,y1,x2,y2), save PNG."""
    from PIL import Image  # local import: optional dep, only needed here

    if output_path is None:
        output_path = f"/tmp/em-region-{int(time.time() * 1000)}.png"
    data = device.exec_out(["screencap", "-p"])
    with Image.open(io.BytesIO(data)) as im:
        x1, y1, x2, y2 = bounds
        crop = im.crop((x1, y1, x2, y2))
        crop.save(output_path)
        w, h = crop.size
    return {"path": output_path, "width": w, "height": h}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/unit/test_screenshot_region.py -v`
Expected: PASS

- [ ] **Step 5: 暴露到 UiModule**

`src/mobilecli/plugin/ctx.py`,`UiModule` 类里(`screenshot` 方法后)加:

```python
    def screenshot_region(
        self, bounds: tuple[int, int, int, int], output_path: str | None = None
    ) -> dict[str, Any]:
        return core_screenshot.capture_region(self.device, bounds, output_path)
```

- [ ] **Step 6: Commit**

```bash
git add src/mobilecli/core/screenshot.py src/mobilecli/plugin/ctx.py tests/unit/test_screenshot_region.py
git commit -m "feat(core): capture_region (screencap + crop) exposed via ctx.ui"
```

### Task 4: core.media.push_to_gallery + MediaModule

**Files:**
- Create: `src/mobilecli/core/media.py`
- Modify: `src/mobilecli/plugin/ctx.py`(新增 `MediaModule` + `ExecContext.media` 字段 + `build`)
- Test: `tests/unit/test_media_push.py`

设计:推完把每个文件 mtime touch 成"现在"且**按 local_paths 顺序递减**(`local_paths[0]` 最新),使相册按给定顺序排到最前(解决 recon 发现的"相册按 mtime 排序、push 保留原 mtime 导致顺序乱"问题)。

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/test_media_push.py`:

```python
"""push_to_gallery: 校验/远端路径/扫描/回查 (mock device)。"""
from __future__ import annotations

import pytest

from mobilecli.core import media
from mobilecli.envelope import EmError, ErrorCode


class _FakeDevice:
    def __init__(self, indexed=True):
        self.pushed = []
        self.shell_cmds = []
        self._indexed = indexed

    def push(self, local, remote, timeout_s=30):
        self.pushed.append((local, remote))

    def shell(self, cmd, timeout_s=30):
        self.shell_cmds.append(cmd)
        if cmd.startswith("content query"):
            return "Row: 0 _id=1, _data=/x\n" if self._indexed else "No result found."
        return ""


def test_rejects_bad_extension(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    with pytest.raises(EmError) as e:
        media.push_to_gallery(_FakeDevice(), [str(f)])
    assert e.value.code == ErrorCode.INVALID_ARG


def test_rejects_missing_file():
    with pytest.raises(EmError) as e:
        media.push_to_gallery(_FakeDevice(), ["/nope/x.jpg"])
    assert e.value.code == ErrorCode.INVALID_ARG


def test_pushes_scans_and_verifies(tmp_path):
    f = tmp_path / "pic.jpg"
    f.write_bytes(b"\xff\xd8\xff")
    dev = _FakeDevice(indexed=True)
    res = media.push_to_gallery(dev, [str(f)], subdir="em-publish")
    assert res["count"] == 1
    assert res["pushed"][0]["remote"] == "/sdcard/DCIM/em-publish/pic.jpg"
    assert res["pushed"][0]["indexed"] is True
    assert any(c.startswith("touch") for c in dev.shell_cmds)
    assert any("MEDIA_SCANNER_SCAN_FILE" in c for c in dev.shell_cmds)


def test_raises_when_not_indexed(tmp_path):
    f = tmp_path / "pic.jpg"
    f.write_bytes(b"\xff\xd8\xff")
    with pytest.raises(EmError) as e:
        media.push_to_gallery(_FakeDevice(indexed=False), [str(f)])
    assert e.value.code == ErrorCode.MEDIA_NOT_INDEXED
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/test_media_push.py -v`
Expected: FAIL — `ModuleNotFoundError: mobilecli.core.media`

- [ ] **Step 3: 实现 core/media.py**

新建 `src/mobilecli/core/media.py`:

```python
"""Push host media into the device gallery so apps' album pickers see it."""
from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.envelope import EmError, ErrorCode

_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
_VIDEO_EXT = {".mp4", ".mov"}
_ALLOWED = _IMAGE_EXT | _VIDEO_EXT
_GALLERY_DIR = "/sdcard/DCIM"


def _is_image(path: str) -> bool:
    return Path(path).suffix.lower() in _IMAGE_EXT


def push_to_gallery(
    device: Device, local_paths: list[str], subdir: str = "em-publish"
) -> dict[str, Any]:
    """Push each local file to /sdcard/DCIM/<subdir>/, set mtime to 'now' in
    descending order (local_paths[0] newest -> sorts first in album), trigger a
    single-file media scan, and verify each is indexed in MediaStore.

    Raises INVALID_ARG (bad ext / missing) or MEDIA_NOT_INDEXED.
    """
    for p in local_paths:
        if not Path(p).is_file():
            raise EmError(ErrorCode.INVALID_ARG, f"media not found: {p}")
        if Path(p).suffix.lower() not in _ALLOWED:
            raise EmError(
                ErrorCode.INVALID_ARG,
                f"unsupported media type: {p}",
                hint=f"allowed: {sorted(_ALLOWED)}",
            )

    remote_dir = f"{_GALLERY_DIR}/{subdir}"
    device.shell(f"mkdir -p {shlex.quote(remote_dir)}")
    pushed: list[dict[str, Any]] = []
    n = len(local_paths)
    for i, local in enumerate(local_paths):
        name = Path(local).name
        remote = f"{remote_dir}/{name}"
        device.push(local, remote)
        # mtime: 现在往前推 (n-1-i) 秒 -> local_paths[0] 最新 -> 相册最前
        # touch -d 用相对时间; BusyBox/toybox 都支持 @epoch 不稳,用 -d "now"... 改用 settimes via -m 不够
        # 用 toybox touch 支持的 'YYYY...'? 最稳:不传时间=now,再对 i>0 的减秒。
        # 简化:全部 touch 成 now(同秒),顺序由 push 先后近似;精确顺序见下方按需细化。
        device.shell(f"touch {shlex.quote(remote)}")
        scan_uri = f"file://{remote}"
        device.shell(
            f"am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE "
            f"-d {shlex.quote(scan_uri)}"
        )
        coll = "video" if not _is_image(local) else "images"
        where = shlex.quote(f"_data='{remote}'")
        q = device.shell(
            f"content query --uri content://media/external/{coll}/media "
            f"--projection _id --where {where}"
        )
        indexed = "Row:" in q
        if not indexed:
            raise EmError(
                ErrorCode.MEDIA_NOT_INDEXED,
                f"pushed but MediaStore did not index: {remote}",
                hint="device may block legacy media scan; check Android version",
            )
        pushed.append({"local": local, "remote": remote, "indexed": True})
    return {"count": len(pushed), "pushed": pushed}
```

> 注:精确 mtime 排序(`touch -d`)各 ROM 语法不一;Pixel/Android16 用 toybox `touch -d @<epoch>` 可行,实施时若需严格顺序在集成阶段按真机 toybox 语法定。v1 先 `touch`=now 让推入素材整体排到相册最前(早于历史素材),组内顺序由 publish verb 在选格子时控制(见 Task 9 `_order_media_for_cover` + 逐格选取)。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/unit/test_media_push.py -v`
Expected: PASS（4 个）

- [ ] **Step 5: 接 MediaModule 到 ExecContext**

`src/mobilecli/plugin/ctx.py`:顶部 import 区加 `from mobilecli.core import media as core_media`;在 `UiModule` 后加:

```python
@dataclass
class MediaModule:
    device: Device

    def push_to_gallery(
        self, local_paths: list[str], subdir: str = "em-publish"
    ) -> dict[str, Any]:
        return core_media.push_to_gallery(self.device, local_paths, subdir)
```

`ExecContext` dataclass 加字段 `media: MediaModule`;`build()` 的构造里加 `media=MediaModule(device=device),`。

- [ ] **Step 6: 跑插件测试确认未回归**

Run: `pytest tests/unit/test_plugin.py tests/unit/test_media_push.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/mobilecli/core/media.py src/mobilecli/plugin/ctx.py tests/unit/test_media_push.py
git commit -m "feat(core): push_to_gallery primitive exposed via ctx.media"
```

---

## Phase 1 — profile(只读)

### Task 5: _parse_profile 纯函数 + fixture

**Files:**
- Create: `tests/fixtures/xhs-profile.xml`
- Modify: `src/mobilecli/apps/xiaohongshu.py`(加 `_parse_profile`)
- Test: `tests/unit/test_xhs_profile.py`

- [ ] **Step 1: 放 fixture**

```bash
cp research/ui-trees/xiaohongshu/22-profile-logged-in.xml tests/fixtures/xhs-profile.xml
```

- [ ] **Step 2: 写失败测试**

新建 `tests/unit/test_xhs_profile.py`:

```python
"""_parse_profile: 从我页 xml 抽登录态/昵称/计数/简介/头像bounds。"""
from __future__ import annotations

from pathlib import Path

from mobilecli.apps.xiaohongshu import _parse_profile

FIX = Path(__file__).parent.parent / "fixtures"


def test_parse_logged_in():
    p = _parse_profile((FIX / "xhs-profile.xml").read_text())
    assert p["logged_in"] is True
    assert p["nickname"] == "测试昵称"
    assert p["red_id"] == "test_red_id"
    assert p["ip"] == "北京"
    assert p["follow_count"] == 2
    assert p["fans_count"] == 29
    assert p["fav_count"] == 197
    assert "测试简介" in p["bio"]
    assert p["avatar_bounds"] is not None
    assert len(p["avatar_bounds"]) == 4


def test_parse_logged_out():
    # 没有 nickname / iv_avatar 节点 -> logged_in False
    xml = '<hierarchy><node resource-id="x" bounds="[0,0][1,1]"/></hierarchy>'
    p = _parse_profile(xml)
    assert p["logged_in"] is False
```

- [ ] **Step 3: 跑测试确认失败**

Run: `pytest tests/unit/test_xhs_profile.py -v`
Expected: FAIL — `ImportError: cannot import name '_parse_profile'`

- [ ] **Step 4: 实现 _parse_profile**

`src/mobilecli/apps/xiaohongshu.py` 顶 import 区补 `from mobilecli.core.ui import find_by_resource_id`(若未导入);加函数:

```python
_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([万亿]?)")


def _to_int(s: str) -> int:
    """'29' -> 29; '1.6万' -> 16000; content-desc '2关注' -> 2."""
    m = _NUM_RE.search(s or "")
    if not m:
        return 0
    val = float(m.group(1))
    unit = m.group(2)
    if unit == "万":
        val *= 10_000
    elif unit == "亿":
        val *= 100_000_000
    return int(val)


def _parse_profile(xml: str) -> dict[str, Any]:
    """Parse the 我/profile tab. logged_in oracle = nickname/iv_avatar present."""
    PFX = "com.xingin.xhs:id/"
    nick = find_by_resource_id(xml, PFX + "profile_new_page_avatar_card_nickname")
    avatar = find_by_resource_id(xml, PFX + "iv_avatar")
    if nick is None and avatar is None:
        return {"logged_in": False}

    redid = find_by_resource_id(xml, PFX + "profile_new_page_avatar_card_redid")
    ip = find_by_resource_id(xml, PFX + "profile_new_page_avatar_card_ip")
    bio = find_by_resource_id(xml, PFX + "userDescTv")
    follow = find_by_resource_id(xml, PFX + "follow_count")
    fans = find_by_resource_id(xml, PFX + "fans_count")
    fav = find_by_resource_id(xml, PFX + "fav_count")

    def _txt(node: dict[str, Any] | None) -> str:
        return (node.get("text") or "").strip() if node else ""

    red_txt = _txt(redid).replace("小红书号：", "").replace("小红书号:", "").strip()
    return {
        "logged_in": True,
        "nickname": _txt(nick),
        "red_id": red_txt,
        "ip": _txt(ip),
        "follow_count": _to_int(_txt(follow)),
        "fans_count": _to_int(_txt(fans)),
        "fav_count": _to_int(_txt(fav)),
        "bio": _txt(bio),
        "avatar_bounds": tuple(avatar["bounds"]) if avatar else None,
    }
```

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/unit/test_xhs_profile.py -v`
Expected: PASS（2 个）。若 `follow_count` 为 0,检查 fixture 里 `follow_count` 节点 text 是否为空 → 改读 `follow_ll` 的 content-desc 兜底(见下 fallback)。

- [ ] **Step 6: 计数兜底(若 Step 5 失败)**

若 `*_count` 节点 text 为空,把 follow/fans/fav 的取值改为先读 `*_count` text,空则读容器 content-desc:

```python
    def _count(count_id: str, ll_id: str) -> int:
        c = find_by_resource_id(xml, PFX + count_id)
        if c and _txt(c):
            return _to_int(_txt(c))
        ll = find_by_resource_id(xml, PFX + ll_id)
        return _to_int(ll.get("content_desc", "")) if ll else 0
    # follow_count=_count("follow_count","follow_ll") 等
```

- [ ] **Step 7: Commit**

```bash
git add src/mobilecli/apps/xiaohongshu.py tests/unit/test_xhs_profile.py tests/fixtures/xhs-profile.xml
git commit -m "feat(xiaohongshu): _parse_profile (login oracle + fields from 我 tab)"
```

### Task 6: profile verb

**Files:**
- Modify: `src/mobilecli/apps/xiaohongshu.py`(加 `profile` verb + 辅助)

- [ ] **Step 1: 实现 profile verb**

`src/mobilecli/apps/xiaohongshu.py` 末尾加:

```python
_ME_TAB_XY = (972, 2288)  # bottom nav 我 (index_me center @1080x2410)


def _dismiss_unfinished_draft(ctx: ExecContext) -> None:
    """若弹「继续编辑笔记吗?」草稿恢复弹窗,点关闭(不存/不编辑)。"""
    xml = Path(ctx.ui.dump()["path"]).read_text()
    btn = ctx.ui.find_by_resource_id(
        xml, "com.xingin.xhs:id/btn_unfinished_draft_dialog_exit"
    )
    if btn is not None:
        ctx.input.tap_node(btn)
        time.sleep(0.8)


def _profile_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--avatar-out", default=None, help="头像 PNG 落盘路径")


@app.verb("profile", add_args=_profile_args)
def profile(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """读取登录态;已登录则返回头像(裁剪PNG)/昵称/小红书号/计数/简介。"""
    ctx.app.ensure_foreground()
    time.sleep(1.0)
    _dismiss_unfinished_draft(ctx)
    ctx.input.tap_xy(*_ME_TAB_XY)  # 我 tab
    time.sleep(2.0)
    _dismiss_unfinished_draft(ctx)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    info = _parse_profile(xml)
    if not info.get("logged_in"):
        return {"logged_in": False}

    bounds = info.pop("avatar_bounds", None)
    if bounds is not None:
        shot = ctx.ui.screenshot_region(bounds, args.avatar_out)
        info["avatar"] = shot["path"]
    else:
        info["avatar"] = None
    return info
```

- [ ] **Step 2: 集成验(真机)**

Run: `EM_SERIAL=5A170DLCH0002P mobilecli xiaohongshu profile --pretty`
Expected: `data.logged_in=true`,`nickname="测试昵称"`,`fans_count=29` 等,`avatar` 指向一个非空 PNG。
验证头像图:`ls -la <avatar path>` 应 >0 字节;打开应是头像方图。

- [ ] **Step 3: Commit**

```bash
git add src/mobilecli/apps/xiaohongshu.py
git commit -m "feat(xiaohongshu): profile verb (login state + avatar/nickname/counts)"
```

---

## Phase 2 — publish

### Task 7: 判型 + 话题解析 + 封面排序(纯函数)

**Files:**
- Modify: `src/mobilecli/apps/xiaohongshu.py`
- Test: `tests/unit/test_xhs_publish_args.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/test_xhs_publish_args.py`:

```python
from __future__ import annotations

import pytest

from mobilecli.apps.xiaohongshu import (
    _classify_media,
    _order_media_for_cover,
    _parse_tags,
)
from mobilecli.envelope import EmError, ErrorCode


def test_classify_images():
    assert _classify_media(["a.jpg", "b.PNG"]) == "image"


def test_classify_single_video():
    assert _classify_media(["v.mp4"]) == "video"


def test_classify_mixed_rejected():
    with pytest.raises(EmError) as e:
        _classify_media(["a.jpg", "v.mp4"])
    assert e.value.code == ErrorCode.INVALID_ARG


def test_classify_multi_video_rejected():
    with pytest.raises(EmError) as e:
        _classify_media(["a.mp4", "b.mp4"])
    assert e.value.code == ErrorCode.INVALID_ARG


def test_parse_tags():
    assert _parse_tags("AI视频, 教程 ,") == ["AI视频", "教程"]
    assert _parse_tags(None) == []


def test_order_media_for_cover_index():
    # 封面=第2张 -> 第2张排首,其余保序
    assert _order_media_for_cover(["a", "b", "c"], cover_index=2) == ["b", "a", "c"]


def test_order_media_for_cover_default():
    assert _order_media_for_cover(["a", "b"], cover_index=None) == ["a", "b"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/test_xhs_publish_args.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: 实现纯函数**

`src/mobilecli/apps/xiaohongshu.py` 加:

```python
_PUB_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
_PUB_VIDEO_EXT = {".mp4", ".mov"}


def _classify_media(paths: list[str]) -> str:
    """全图片->'image';恰好1视频且无图->'video';否则 INVALID_ARG。"""
    from pathlib import Path as _P

    exts = [_P(p).suffix.lower() for p in paths]
    imgs = [e for e in exts if e in _PUB_IMAGE_EXT]
    vids = [e for e in exts if e in _PUB_VIDEO_EXT]
    bad = [e for e in exts if e not in _PUB_IMAGE_EXT | _PUB_VIDEO_EXT]
    if bad:
        raise EmError(ErrorCode.INVALID_ARG, f"unsupported media: {bad}")
    if imgs and not vids:
        return "image"
    if len(vids) == 1 and not imgs:
        return "video"
    raise EmError(
        ErrorCode.INVALID_ARG,
        "media must be all images OR exactly one video (no mix)",
    )


def _parse_tags(s: str | None) -> list[str]:
    if not s:
        return []
    return [t.strip() for t in s.split(",") if t.strip()]


def _order_media_for_cover(
    media: list[str], cover_index: int | None
) -> list[str]:
    """图文:把封面图排到首位(选中顺序=展示顺序,首张=封面)。"""
    if cover_index is None or cover_index < 1 or cover_index > len(media):
        return list(media)
    i = cover_index - 1
    return [media[i]] + media[:i] + media[i + 1 :]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/unit/test_xhs_publish_args.py -v`
Expected: PASS（7 个）

- [ ] **Step 5: Commit**

```bash
git add src/mobilecli/apps/xiaohongshu.py tests/unit/test_xhs_publish_args.py
git commit -m "feat(xiaohongshu): publish arg pure-fns (classify/tags/cover-order)"
```

### Task 8: publish caps + verb 骨架(参数 + 判型 + lint + 推素材 + dry-run 返回)

**Files:**
- Modify: `src/mobilecli/apps/xiaohongshu.py`(caps 加 `publish:3`;加 `publish` verb)

- [ ] **Step 1: caps 加 publish**

`app = App(...)` 的 `daily_caps` 字典加一行:`"publish": 3,`(来源 docs/anti-risk-control.md Notes posted ≤3/day)。

- [ ] **Step 2: 加 publish verb 入口(参数 + 校验 + 推素材 + 进相册)**

`src/mobilecli/apps/xiaohongshu.py` 末尾加常量与 verb。selector 全部来自 `00-selectors-publish.md`:

```python
# publish-flow selectors (00-selectors-publish.md)
_PUB = {
    "post_entry": (540, 2288),          # id/index_post
    "album_from_gallery": (540, 1775),  # 面板 id/rlFirst 从相册选择
    "go_next": "com.xingin.xhs:id/bottomGoNext",        # 选完下一步
    "video_edit_next": "com.xingin.xhs:id/capa_light_edit_next",
    "title": "com.xingin.xhs:id/editTitle",
    "body": "com.xingin.xhs:id/postNoteEditContentView",
    "add_topic": "com.xingin.xhs:id/addTopicView",
    "topic_name": "com.xingin.xhs:id/tvTopicName",
    "cover_entry": "com.xingin.xhs:id/bottomEditCoverAreaV2",
    "cover_album_btn": "com.xingin.xhs:id/album_cover_layout",
    "cover_thumb": "com.xingin.xhs:id/thumbnailIv",
    "cover_done": "com.xingin.xhs:id/btnDone",
    "cover_edit_done": "com.xingin.xhs:id/rightTv",
    "publish_btn": "com.xingin.xhs:id/capaBigPostBtn",
    "loc_refuse": "com.xingin.xhs:id/text_refuse",
    "select_circle": "com.xingin.xhs:id/selectableLayout",
    "no_perm_text": "去开启权限",
}


def _publish_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--media", nargs="+", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--tags", default=None)
    p.add_argument("--cover", default=None, help="图文: 第N张(int); 视频: 封面图路径")
    p.add_argument(
        "--declare",
        default="none",
        choices=["none", "ai", "original", "repost", "fiction", "marketing", "opinion"],
    )


_DECLARE_TEXT = {
    "ai": "含 AI 合成内容",
    "original": "内容为自行拍摄",
    "repost": "内容为转载",
    "fiction": "含虚构演绎内容",
    "marketing": "内容含营销信息",
    "opinion": "个人观点，仅供参考",
}


@app.verb("publish", add_args=_publish_args, requires_commit_flag=True)
def publish(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """发布图文/视频。默认 dry-run(走到发布键前停);--commit 真发。"""
    # 1. lint + 判型 + cover 参数合法性
    ctx.linter.check_or_raise(args.title)
    ctx.linter.check_or_raise(args.body)
    tags = _parse_tags(args.tags)
    for t in tags:
        ctx.linter.check_or_raise(t)
    media_type = _classify_media(args.media)

    cover_index = None
    cover_path = None
    if args.cover is not None:
        if media_type == "image":
            if not args.cover.isdigit():
                raise EmError(ErrorCode.INVALID_ARG, "图文 --cover 需为第N张(整数)")
            cover_index = int(args.cover)
        else:
            cover_path = args.cover
            _classify_media([cover_path])  # 复用扩展名校验(单文件)

    # 2. 推素材(图文按封面顺序;视频单个;cover_path 一并推)
    media = args.media
    if media_type == "image":
        media = _order_media_for_cover(media, cover_index)
    to_push = list(media) + ([cover_path] if cover_path else [])
    pushed = ctx.media.push_to_gallery(to_push)

    if args.commit:
        ctx.governor.check_or_raise("publish")

    steps: list[str] = [f"pushed {pushed['count']} media ({media_type})"]

    # 3. 进相册
    _ensure_home(ctx)
    ctx.input.tap_xy(*_PUB["post_entry"]); time.sleep(2)
    ctx.input.tap_xy(*_PUB["album_from_gallery"]); time.sleep(3)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    if _PUB["no_perm_text"] in xml:
        raise EmError(
            ErrorCode.PERMISSION_REQUIRED,
            "小红书无完整相册权限,无法读取推入素材",
            hint="adb shell pm grant com.xingin.xhs android.permission.READ_MEDIA_IMAGES "
                 "&& ...READ_MEDIA_VIDEO",
        )
    steps.append("opened album")

    # 4. 选素材(前 len(media) 格,row-major;详见 Task 9)
    _select_pushed_media(ctx, count=len(media))
    steps.append(f"selected {len(media)} item(s)")

    # ---- 余下编排见 Task 9/10;此处先返回占位以便分步提交 ----
    return {"dry_run": not args.commit, "committed": bool(args.commit),
            "media_type": media_type, "pushed": pushed["pushed"], "steps": steps,
            "_incomplete": "see Task 9/10"}
```

> 注:`_ensure_home` 小红书版需存在;若 `apps/xiaohongshu.py` 已有 home 导航助手则复用,否则照 douyin `_ensure_home` 模式加一个(launch+back 回 `IndexActivityV2`)。`_select_pushed_media` 在 Task 9 实现。

- [ ] **Step 3: 加 _select_pushed_media + _ensure_home(若缺)**

```python
def _ensure_home(ctx: ExecContext, max_back: int = 5) -> None:
    ctx.app.ensure_foreground(); time.sleep(0.5)
    _dismiss_unfinished_draft(ctx)
    for _ in range(max_back):
        act = str(ctx.app.foreground().get("activity", ""))
        if act.endswith(_HOME_ACTIVITY_SUFFIX):
            return
        ctx.input.keyevent("back"); time.sleep(0.8)


def _select_pushed_media(ctx: ExecContext, count: int) -> None:
    """点前 count 个网格单元的选择圈(推入素材已 touch 到相册最前)。"""
    xml = Path(ctx.ui.dump()["path"]).read_text()
    circles = ctx.ui.find_all_by_resource_id(xml, _PUB["select_circle"])
    if len(circles) < count:
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            f"album shows {len(circles)} selectable items, need {count}",
            hint="pushed media not visible; check READ_MEDIA permission / scan",
        )
    for i in range(count):
        ctx.input.tap_node(circles[i]); time.sleep(0.6)
    go = ctx.ui.find_by_resource_id(Path(ctx.ui.dump()["path"]).read_text(), _PUB["go_next"])
    if go is None:
        raise EmError(ErrorCode.ELEMENT_NOT_FOUND, "下一步 button not found")
    ctx.input.tap_node(go); time.sleep(3)
```

- [ ] **Step 4: 跑单测确认未回归**

Run: `pytest tests/unit/ -v`
Expected: 全 PASS（verb 体未单测,纯函数已覆盖)

- [ ] **Step 5: Commit**

```bash
git add src/mobilecli/apps/xiaohongshu.py
git commit -m "feat(xiaohongshu): publish verb skeleton (args/lint/classify/push/album-select)"
```

### Task 9: 编辑页填充(标题/正文/话题/声明)+ 视频前段 + 封面

**Files:**
- Modify: `src/mobilecli/apps/xiaohongshu.py`(补全 publish verb 编排)

- [ ] **Step 1: 加编辑页填充助手**

```python
def _type_cjk(ctx: ExecContext, node: dict[str, Any], text: str) -> None:
    """点输入框 + ADBKeyboard 输入 + 回查重试(reply verb 同款 IME 处理)。"""
    needs_cjk = not text.isascii()
    prev = _ime.current_ime(ctx.device) if needs_cjk else None
    if needs_cjk:
        _ime.set_adbkeyboard(ctx.device); time.sleep(0.6)
    try:
        ctx.input.tap_node(node); time.sleep(1.0)
        for attempt in range(2):
            if needs_cjk:
                ctx.device.shell(
                    f"am broadcast -a ADB_INPUT_TEXT --es msg {shlex.quote(text)}"
                )
            else:
                ctx.input.type_text(text)
            time.sleep(1.2)
            xml = Path(ctx.ui.dump()["path"]).read_text()
            if text[:6] in xml:  # 回查前几字落地
                return
    finally:
        if needs_cjk and prev:
            _ime.restore_ime(ctx.device, prev)


def _add_topics(ctx: ExecContext, tags: list[str]) -> list[bool]:
    linked: list[bool] = []
    for t in tags:
        xml = Path(ctx.ui.dump()["path"]).read_text()
        btn = ctx.ui.find_by_resource_id(xml, _PUB["add_topic"])
        if btn is None:
            linked.append(False); continue
        ctx.input.tap_node(btn); time.sleep(1.0)
        _ime.set_adbkeyboard(ctx.device); time.sleep(0.4)
        ctx.device.shell(f"am broadcast -a ADB_INPUT_TEXT --es msg {shlex.quote(t)}")
        time.sleep(1.5)
        xml = Path(ctx.ui.dump()["path"]).read_text()
        rows = ctx.ui.find_all_by_resource_id(xml, _PUB["topic_name"])
        if rows:
            ctx.input.tap_node(rows[0]); time.sleep(1.0); linked.append(True)
        else:
            linked.append(False)
    return linked


def _set_declare(ctx: ExecContext, declare: str) -> None:
    if declare == "none":
        return
    xml = Path(ctx.ui.dump()["path"]).read_text()
    entry = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/declareTv")
    if entry is None:
        return
    ctx.input.tap_node(entry); time.sleep(2.0)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    opt = ctx.ui.find_by_text(xml, _DECLARE_TEXT[declare])
    if opt is not None:
        ctx.input.tap_node(opt); time.sleep(0.8)
    ctx.input.keyevent("back"); time.sleep(1.0)  # 回编辑页


def _set_video_cover(ctx: ExecContext, cover_path_name: str) -> None:
    """视频自定义封面:选封面->+相册->选图->下一步->制作封面完成。"""
    xml = Path(ctx.ui.dump()["path"]).read_text()
    entry = ctx.ui.find_by_resource_id(xml, _PUB["cover_entry"])
    if entry is None:
        return
    ctx.input.tap_node(entry); time.sleep(2.5)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    alb = ctx.ui.find_by_resource_id(xml, _PUB["cover_album_btn"])
    if alb is None:
        ctx.input.keyevent("back"); return
    ctx.input.tap_node(alb); time.sleep(3)
    # 封面相册:推入的封面图已 touch 到最前 -> 选第一张 thumbnail
    xml = Path(ctx.ui.dump()["path"]).read_text()
    thumbs = ctx.ui.find_all_by_resource_id(xml, _PUB["cover_thumb"])
    if thumbs:
        ctx.input.tap_node(thumbs[0]); time.sleep(3)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    done = ctx.ui.find_by_resource_id(xml, _PUB["cover_done"])
    if done:
        ctx.input.tap_node(done); time.sleep(3)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    edit_done = ctx.ui.find_by_resource_id(xml, _PUB["cover_edit_done"])
    if edit_done:
        ctx.input.tap_node(edit_done); time.sleep(2.5)
```

- [ ] **Step 2: 替换 Task 8 的占位返回,补全 verb 主体**

把 Task 8 verb 里 `# ---- 余下编排` 之后的占位 return 换成:

```python
    # 5. 视频专属:编辑页 -> 下一步
    if media_type == "video":
        xml = Path(ctx.ui.dump()["path"]).read_text()
        nxt = ctx.ui.find_by_resource_id(xml, _PUB["video_edit_next"])
        if nxt is None:
            raise EmError(ErrorCode.ELEMENT_NOT_FOUND, "video edit 下一步 not found")
        ctx.input.tap_node(nxt); time.sleep(3)
        steps.append("passed video edit")

    # 6. 编辑页:取消位置弹窗
    xml = Path(ctx.ui.dump()["path"]).read_text()
    refuse = ctx.ui.find_by_resource_id(xml, _PUB["loc_refuse"])
    if refuse is not None:
        ctx.input.tap_node(refuse); time.sleep(1.5)

    # 7. 标题 + 正文
    xml = Path(ctx.ui.dump()["path"]).read_text()
    title_node = ctx.ui.find_by_resource_id(xml, _PUB["title"])
    body_node = ctx.ui.find_by_resource_id(xml, _PUB["body"])
    if title_node is None or body_node is None:
        raise EmError(ErrorCode.ELEMENT_NOT_FOUND, "compose title/body not found",
                      hint="check 00-selectors-publish.md CapaPostNotePlatformActivity")
    _type_cjk(ctx, title_node, args.title)
    body_node = ctx.ui.find_by_resource_id(Path(ctx.ui.dump()["path"]).read_text(), _PUB["body"])
    _type_cjk(ctx, body_node, args.body)
    steps.append("filled title+body")

    # 8. 话题
    tags_linked = _add_topics(ctx, tags) if tags else []
    if tags:
        steps.append(f"topics linked={tags_linked}")

    # 9. 视频自定义封面
    if media_type == "video" and cover_path:
        _set_video_cover(ctx, Path(cover_path).name)
        steps.append("set custom cover")

    # 10. 声明
    if args.declare != "none":
        _set_declare(ctx, args.declare); steps.append(f"declare={args.declare}")

    # 11. 收键盘 + 定位发布键
    ctx.input.keyevent("back"); time.sleep(1.0)  # 收键盘
    xml = Path(ctx.ui.dump()["path"]).read_text()
    pub_btn = ctx.ui.find_by_resource_id(xml, _PUB["publish_btn"])
    if pub_btn is None:
        raise EmError(ErrorCode.ELEMENT_NOT_FOUND, "发布笔记 button not found")
    steps.append("reached 发布笔记")
    shot = ctx.ui.screenshot()["path"]

    base = {
        "media_type": media_type, "pushed": pushed["pushed"],
        "title": args.title, "body_len": len(args.body),
        "tags": tags, "tags_linked": tags_linked,
        "cover": (f"index:{cover_index}" if cover_index else
                  f"path:{cover_path}" if cover_path else "default"),
        "declare": args.declare, "steps": steps, "screenshot": shot,
        "publish_button_cx": pub_btn["cx"], "publish_button_cy": pub_btn["cy"],
    }
    if not args.commit:
        ctx.app.force_stop()  # 放弃草稿(不存不发)
        return {"dry_run": True, "committed": False, **base}

    ctx.input.tap_node(pub_btn); time.sleep(5)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    verified = str(ctx.app.foreground().get("activity", "")).endswith(_HOME_ACTIVITY_SUFFIX) \
        or "发布成功" in xml
    ctx.governor.record("publish")
    return {"dry_run": False, "committed": True, "verified_published": verified, **base}
```

- [ ] **Step 3: 跑单测确认未回归**

Run: `pytest tests/unit/ -v`
Expected: 全 PASS

- [ ] **Step 4: Commit**

```bash
git add src/mobilecli/apps/xiaohongshu.py
git commit -m "feat(xiaohongshu): publish verb full orchestration (compose/topic/cover/declare/declare)"
```

### Task 10: 集成验证(真机 dry-run)

**Files:** 无(真机跑 CLI)

- [ ] **Step 1: 视频 dry-run**

Run:
```bash
EM_SERIAL=5A170DLCH0002P mobilecli xiaohongshu publish \
  --media /Users/crawford/workspace/原素材.mp4 \
  --title "自动化测试标题" --body "自动化发布流程测试，请勿发布。" \
  --tags "AI视频" --cover /tmp/em_test_img.jpg --pretty
```
Expected: `dry_run:true`,`media_type:"video"`,`steps` 含 reached 发布笔记,`screenshot` 指向待发布截图;手机最终被 force-stop(草稿丢弃)。
人工核对截图:标题/正文/话题/自定义封面齐全。

- [ ] **Step 2: 图文 dry-run**

准备 2 张测试图(`ffmpeg -f lavfi -i color=c=red:s=1080x1440 -frames:v 1 /tmp/p1.jpg` 等),Run:
```bash
EM_SERIAL=5A170DLCH0002P mobilecli xiaohongshu publish \
  --media /tmp/p1.jpg /tmp/p2.jpg --title "图文测试" --body "图文 dry-run #AI视频" \
  --tags "AI视频" --cover 2 --pretty
```
Expected: `media_type:"image"`,直达编辑页(无 video edit step),封面=第2张(p2 排首)。

- [ ] **Step 2.5: 修正(预期内的真机偏差)**

若某步 selector 失效 / 时序不够:对照 `00-selectors-publish.md` 修 `_PUB` 坐标或 `time.sleep`,重跑。常见:话题列表加载慢→加 sleep;`go_next` 选完才出现→已在 `_select_pushed_media` 重 dump。

- [ ] **Step 3: Commit(若有真机修正)**

```bash
git add src/mobilecli/apps/xiaohongshu.py
git commit -m "fix(xiaohongshu): publish selectors/timing per real-device dry-run"
```

### Task 11: 文档

**Files:**
- Modify: `README.md`(CLI 命令全表)
- Modify: `research/ui-trees/xiaohongshu/00-selectors-publish.md`(补图文流真机结果)

- [ ] **Step 1: README**

在 `mobilecli xiaohongshu` 子命令表加:

```
| `mobilecli xiaohongshu profile [--avatar-out PATH]` | 读登录态 + 头像/昵称/计数 | 只读 |
| `mobilecli xiaohongshu publish --media P... --title T --body B [--tags] [--cover] [--declare] [--commit]` | 发布图文/视频 | 默认 dry-run；`--commit` 需 `EM_ALLOW_COMMIT=1` |
```

- [ ] **Step 2: 补 selectors 图文实测**

把 Task 10 Step 2 图文 dry-run 的真机确认(直达编辑页 / 封面=首图)补进 `00-selectors-publish.md` §「图文流」。

- [ ] **Step 3: Commit**

```bash
git add README.md research/ui-trees/xiaohongshu/00-selectors-publish.md
git commit -m "docs: xiaohongshu profile + publish verbs (CLI table + selectors)"
```

---

## Self-Review notes

- **Spec 覆盖**:profile(登录态/头像裁剪/字段)✓ Task 5-6;publish 地基(media push)✓ Task 4;判型/话题/封面 ✓ Task 7-9;`--declare` ✓ Task 9;Android16 权限检测 ✓ Task 8;位置弹窗 ✓ Task 9;CJK 回查 ✓ Task 9;cap=3 ✓ Task 8;双闸 ✓(`requires_commit_flag` + verb 内 commit 分支)。
- **新增 ErrorCode** 先于使用(Task 1)✓。
- **类型/命名一致**:`_PUB` 选择器 dict、`push_to_gallery` 返回 `{count,pushed:[{local,remote,indexed}]}`、`_parse_profile` 返回含 `avatar_bounds`(verb 内 pop)— 前后一致。
- **已知真机偏差**:Task 10 Step 2.5 显式留口子修 selector/时序(发布链路是新捕获,集成阶段定);commit 路径默认不在自动化测试跑(避免污染真实账号),由用户显式授权单验。
