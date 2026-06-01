# 抖音 like + 抖音/小红书 reply(二级追评)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `mobilecli` 新增抖音 `like`、抖音 `reply`、小红书 `reply`(二级评论追评)三个真机 verb。

**Architecture:** 纯函数解析评论区 XML → `CommentRow{index,text,reply_node}` 列表(共享 `select_comment` 按 rank/match 二选一选中)→ verb 编排「确保评论区可见 → 解析 → 选中 → 点回复 → 输入 → dry-run/commit」。纯函数用已捕获 fixture 单测;device-bound verb 用 `EM_INTEGRATION` 真机集成测试验。

**Tech Stack:** Python 3.14、argparse plugin verb(`@app.verb`)、`uiautomator dump` XML、pytest(`uv run pytest`)、ADBKeyboard(CJK 输入,`type_text_humanized` 内置)。

**事实源:** 设计 spec `docs/superpowers/specs/2026-06-01-douyin-like-xhs-douyin-reply-design.md`;selector `research/ui-trees/{douyin,xiaohongshu}/00-selectors.md`。

**测试运行:** 单测 `uv run pytest tests/unit/<file> -q`;集成(真机)`EM_INTEGRATION=1 uv run pytest tests/integration/<file> -q`;真发(E2E)`EM_E2E=1 EM_ALLOW_COMMIT=1 uv run pytest ... -q`。

---

## 文件结构

| 文件 | 责任 | 动作 |
|---|---|---|
| `tests/fixtures/douyin-comments.xml` | 抖音评论浮层 dump(测试用) | Create(从 research 拷) |
| `tests/fixtures/xhs-comments.xml` | 小红书评论区 dump(测试用) | Create(从 research 拷) |
| `src/mobilecli/apps/_comments.py` | `CommentRow` + `select_comment`(共享纯逻辑) | Create |
| `tests/unit/test_comments_select.py` | `select_comment` 分支单测 | Create |
| `tests/unit/test_douyin_comments.py` | 抖音 `_parse_comment_rows` 单测 | Create |
| `tests/unit/test_xhs_comments.py` | 小红书 `_parse_comment_rows` 单测 | Create |
| `src/mobilecli/apps/douyin.py` | + `_parse_comment_rows` + `like` + `reply` verb | Modify |
| `src/mobilecli/apps/xiaohongshu.py` | + `_parse_comment_rows` + `reply` verb | Modify |
| `tests/integration/test_douyin_engage.py` | 抖音 like/reply 真机集成 | Create |
| `tests/integration/test_xhs_reply.py` | 小红书 reply 真机集成 | Create |
| `research/ui-trees/{douyin,xiaohongshu}/00-selectors.md` | 新 verb 映射文档 | Modify |

---

## Task 1: 评论区 fixture

**Files:**
- Create: `tests/fixtures/douyin-comments.xml`(从 `research/ui-trees/douyin/06-comments-panel.xml` 拷)
- Create: `tests/fixtures/xhs-comments.xml`(从 `research/ui-trees/xiaohongshu/05-comments-area.xml` 拷)

- [ ] **Step 1: 拷贝 fixture**

```bash
cp research/ui-trees/douyin/06-comments-panel.xml tests/fixtures/douyin-comments.xml
cp research/ui-trees/xiaohongshu/05-comments-area.xml tests/fixtures/xhs-comments.xml
```

- [ ] **Step 2: 验证可读 + 含关键节点**

Run(fixture 是单行 XML,必须用 `grep -o | wc -l` 数出现次数,`grep -c` 只数行会返回 1):
```bash
grep -o 'id/xdh' tests/fixtures/douyin-comments.xml | wc -l        # 期望 3
grep -o 'id/tv_content' tests/fixtures/xhs-comments.xml | wc -l    # 期望 4
```
Expected: 抖音 `3`(3 个可见回复键);小红书 `4`(含 1 个子楼 `x=215`,Task 6 解析后顶层只剩 3,不矛盾)。

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/douyin-comments.xml tests/fixtures/xhs-comments.xml
git commit -m "test: 评论区 dump fixture(抖音浮层 + 小红书评论区)"
```

---

## Task 2: 共享 `_comments.py` — CommentRow + select_comment

**Files:**
- Create: `src/mobilecli/apps/_comments.py`
- Test: `tests/unit/test_comments_select.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_comments_select.py
"""Offline tests for comment-row selection (rank / match)."""

from __future__ import annotations

import pytest

from mobilecli.apps._comments import CommentRow, select_comment
from mobilecli.envelope import EmError, ErrorCode


def _rows() -> list[CommentRow]:
    return [
        CommentRow(index=1, text="用户A,第一条评论", reply_node={"cx": 10, "cy": 10}),
        CommentRow(index=2, text="用户B,多少钱啊", reply_node={"cx": 20, "cy": 20}),
        CommentRow(index=3, text="用户C,第三条", reply_node={"cx": 30, "cy": 30}),
    ]


def test_select_by_rank_returns_nth():
    row = select_comment(_rows(), rank=2, match=None)
    assert row.index == 2
    assert row.reply_node["cy"] == 20


def test_select_by_match_returns_first_containing():
    row = select_comment(_rows(), rank=None, match="多少钱")
    assert row.index == 2


def test_rank_out_of_range_raises_element_not_found():
    with pytest.raises(EmError) as ei:
        select_comment(_rows(), rank=9, match=None)
    assert ei.value.code == ErrorCode.ELEMENT_NOT_FOUND


def test_match_no_hit_raises_element_not_found():
    with pytest.raises(EmError) as ei:
        select_comment(_rows(), rank=None, match="不存在")
    assert ei.value.code == ErrorCode.ELEMENT_NOT_FOUND


def test_neither_rank_nor_match_raises_unknown():
    with pytest.raises(EmError) as ei:
        select_comment(_rows(), rank=None, match=None)
    assert ei.value.code == ErrorCode.UNKNOWN


def test_both_rank_and_match_raises_unknown():
    with pytest.raises(EmError) as ei:
        select_comment(_rows(), rank=1, match="第一条")
    assert ei.value.code == ErrorCode.UNKNOWN
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_comments_select.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'mobilecli.apps._comments'`

- [ ] **Step 3: 写最小实现**

```python
# src/mobilecli/apps/_comments.py
"""Shared comment-row model + target selection for reply verbs.

Pure logic over already-parsed UI nodes; no device access (testable with
fixture XML). Platform-specific `_parse_comment_rows(xml)` lives in each app.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mobilecli.envelope import EmError, ErrorCode


@dataclass
class CommentRow:
    index: int                  # 1-based, among currently-visible top-level comments
    text: str                   # matchable text (username + body + meta)
    reply_node: dict[str, Any]  # the row's 回复 affordance node (bounds/cx/cy)
    content_node: dict[str, Any] | None = None  # comment-text node (XHS reply tap fallback)


def select_comment(
    rows: list[CommentRow],
    *,
    rank: int | None = None,
    match: str | None = None,
) -> CommentRow:
    """Pick exactly one comment row by rank (1-based) or by text substring match.

    Exactly one of rank/match must be given. Raises EmError otherwise / on miss.
    """
    if (rank is None) == (match is None):
        raise EmError(
            ErrorCode.UNKNOWN,
            "reply requires exactly one of --rank / --match",
            hint='pass --rank N or --match "keyword", not both / neither',
        )
    if rank is not None:
        if rank < 1 or rank > len(rows):
            raise EmError(
                ErrorCode.ELEMENT_NOT_FOUND,
                f"rank {rank} out of range (have {len(rows)} visible comments)",
                hint="scroll comments into view or lower --rank",
            )
        return rows[rank - 1]
    for row in rows:
        if match in row.text:
            return row
    raise EmError(
        ErrorCode.ELEMENT_NOT_FOUND,
        f"no visible comment contains {match!r}",
        hint="keyword not found among currently-visible comments",
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_comments_select.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/mobilecli/apps/_comments.py tests/unit/test_comments_select.py
git commit -m "feat(apps): CommentRow + select_comment(rank/match)"
```

---

## Task 3: 抖音 `_parse_comment_rows`(fco∋xdh 几何包含)

**Files:**
- Modify: `src/mobilecli/apps/douyin.py`(新增 import + helper)
- Test: `tests/unit/test_douyin_comments.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_douyin_comments.py
"""Offline tests for Douyin comment-row parsing -- uses fixture XML."""

from __future__ import annotations

from pathlib import Path

from mobilecli.apps.douyin import _parse_comment_rows

FIX = Path(__file__).parent.parent / "fixtures"


def _xml() -> str:
    return (FIX / "douyin-comments.xml").read_text()


def test_parses_visible_toplevel_rows():
    rows = _parse_comment_rows(_xml())
    # 3 个可见回复键(末行 fco 的 xdh 被 RecyclerView 底边裁掉)
    assert len(rows) == 3
    assert [r.index for r in rows] == [1, 2, 3]


def test_row_text_comes_from_fco_content_desc():
    rows = _parse_comment_rows(_xml())
    assert "我看上他了" in rows[0].text
    assert "女主好美" in rows[1].text
    assert "跪求一双" in rows[2].text


def test_reply_node_center_inside_its_fco():
    rows = _parse_comment_rows(_xml())
    # 第一行回复键中心落在 [0,1055][1080,1330] 区间
    n = rows[0].reply_node
    assert 0 <= n["cx"] <= 1080
    assert 1055 <= n["cy"] <= 1330
    assert n["text"] == "回复"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_douyin_comments.py -q`
Expected: FAIL — `ImportError: cannot import name '_parse_comment_rows'`

- [ ] **Step 3: 写最小实现** — 在 `src/mobilecli/apps/douyin.py` 顶部 import 区加:

```python
from mobilecli.apps._comments import CommentRow, select_comment
from mobilecli.core.ui import find_all_by_resource_id
```

在文件 `# ----- comment ---` 区块**之前**(`back` verb 之后)加:

```python
# ----- comments (shared parse for reply) ----------------------------------------

_FCO_ID = "com.ss.android.ugc.aweme:id/fco"
_XDH_ID = "com.ss.android.ugc.aweme:id/xdh"


def _bounds_contains(outer: list[int] | None, cx: int, cy: int) -> bool:
    if not outer:
        return False
    return outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]


def _parse_comment_rows(xml: str) -> list[CommentRow]:
    """Parse top-level comment rows from the comments overlay.

    Each top-level comment is an `fco` FrameLayout whose content-desc is the
    whole comment string; its 回复 button is an `xdh` inside it. Anchor on xdh
    (guarantees a tappable target) and pair to the enclosing fco for text.
    Partially-scrolled last rows have an fco but no xdh -> naturally dropped.
    """
    fcos = find_all_by_resource_id(xml, _FCO_ID)
    xdhs = find_all_by_resource_id(xml, _XDH_ID)
    rows: list[CommentRow] = []
    for xdh in xdhs:
        container = next(
            (f for f in fcos if _bounds_contains(f["bounds"], xdh["cx"], xdh["cy"])),
            None,
        )
        text = container["content_desc"] if container else ""
        rows.append(CommentRow(index=len(rows) + 1, text=text, reply_node=xdh))
    return rows
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_douyin_comments.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/mobilecli/apps/douyin.py tests/unit/test_douyin_comments.py
git commit -m "feat(douyin): _parse_comment_rows(fco∋xdh)"
```

---

## Task 4: 抖音 `like` verb

**Files:**
- Modify: `src/mobilecli/apps/douyin.py`(新增 `like` verb;`daily_caps['like']=200` 已存在)
- Test: `tests/integration/test_douyin_engage.py`(真机,gated)

- [ ] **Step 1: 写实现** — 在 `douyin.py` 的 `back` verb 之后、`comment` verb 之前加:

```python
# ----- like ---------------------------------------------------------------------


@app.verb("like", requires_commit_flag=True)
def like(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Like the current video detail.

    Default = dry-run (locate like button, return coords).
    With --commit (and EM_ALLOW_COMMIT=1 gated by cli), actually tap.
    """
    ctx.governor.check_or_raise("like")

    xml = Path(ctx.ui.dump()["path"]).read_text()
    like_btn = ctx.ui.find_by_resource_id(xml, "com.ss.android.ugc.aweme:id/gl1")
    if like_btn is None:
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            "Douyin like button not visible",
            hint="open a video detail first via `douyin open --rank N`",
        )

    before_liked = "已点赞" in like_btn.get("content_desc", "")

    if not getattr(args, "commit", False):
        return {
            "dry_run": True,
            "committed": False,
            "already_liked": before_liked,
            "like_button_cx": like_btn["cx"],
            "like_button_cy": like_btn["cy"],
        }

    ctx.input.tap_node(like_btn)
    time.sleep(1.5)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    after = ctx.ui.find_by_resource_id(xml, "com.ss.android.ugc.aweme:id/gl1")
    after_liked = "已点赞" in (after.get("content_desc", "") if after else "")
    ctx.governor.record("like")
    return {
        "dry_run": False,
        "committed": True,
        "already_liked_before": before_liked,
        "already_liked_after": after_liked,
        "verified_changed": before_liked != after_liked,
    }
```

- [ ] **Step 2: 单测无回归 + verb 已注册**

Run: `uv run pytest tests/unit -q`
Expected: PASS(全绿)。
Run: `uv run mobilecli douyin --help`
Expected: 帮助里 verbs 含 `like`。

- [ ] **Step 3: 写集成测试(gated)**

```python
# tests/integration/test_douyin_engage.py
"""Douyin like/reply integration -- EM_INTEGRATION=1 + connected device.

These DO NOT commit (dry-run only). Real-send is exercised manually / E2E.
Pre-req: app open on a video detail (run `douyin search`/`open` first by hand,
or set EM_DOUYIN_KEYWORD to let the test navigate)."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest


def _cli(*args: str) -> dict:
    r = subprocess.run(
        [sys.executable, "-m", "mobilecli", *args],
        capture_output=True, text=True, check=False,
    )
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def serial() -> str:
    r = subprocess.run(["adb", "devices"], capture_output=True, text=True, check=False)
    online = [ln.split("\t")[0].strip() for ln in r.stdout.splitlines() if "\tdevice" in ln]
    if not online:
        pytest.skip("no device connected")
    return online[0]


@pytest.mark.integration
def test_douyin_like_dry_run_locates_button(serial: str):
    """Requires a video detail already open. dry-run returns button coords."""
    _cli("--serial", serial, "douyin", "launch")
    _cli("--serial", serial, "douyin", "search", "--keyword", os.environ.get("EM_DOUYIN_KEYWORD", "猫"))
    _cli("--serial", serial, "douyin", "open", "--rank", "1")
    payload = _cli("--serial", serial, "douyin", "like")  # no --commit
    assert payload["ok"] is True, payload
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["like_button_cx"] > 0
```

- [ ] **Step 4: 真机跑集成(dry-run)**

Run: `EM_INTEGRATION=1 uv run pytest tests/integration/test_douyin_engage.py::test_douyin_like_dry_run_locates_button -q`
Expected: PASS(手机上能看到搜索→打开视频→定位到点赞键坐标)。
> 若失败:`uv run mobilecli --serial <S> screenshot -o /tmp/s.png` 看当前界面,核对 `gl1` 是否仍是点赞键(抖音 rid 可能漂移)。

- [ ] **Step 5: 真发验证(手动,一次)**

```bash
EM_ALLOW_COMMIT=1 uv run mobilecli --serial <S> douyin like --commit --pretty
```
Expected: `verified_changed: true`,手机上爱心变红。

- [ ] **Step 6: Commit**

```bash
git add src/mobilecli/apps/douyin.py tests/integration/test_douyin_engage.py
git commit -m "feat(douyin): like verb + integration test"
```

---

## Task 5: 抖音 `reply` verb

**Files:**
- Modify: `src/mobilecli/apps/douyin.py`(新增 `reply` verb)
- Test: `tests/integration/test_douyin_engage.py`(追加 reply dry-run)

- [ ] **Step 1: 写实现** — 在 `douyin.py` 末尾(`comment` verb 之后)加:

```python
# ----- reply (二级追评) ---------------------------------------------------------


def _reply_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--rank", type=int, help="reply to the Nth visible comment")
    p.add_argument("--match", help="reply to first visible comment containing this text")
    p.add_argument("--text", required=True)


@app.verb("reply", add_args=_reply_args, requires_commit_flag=True)
def reply(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Reply to a comment on the current video (creates a 2nd-level reply).

    Select target by --rank N or --match "kw" (exactly one). Default = dry-run
    (locate target + send button, cancel). --commit actually sends.
    """
    ctx.linter.check_or_raise(args.text)
    ctx.governor.check_or_raise("comment")

    # Ensure the comments overlay is open (parse; if empty, tap comment icon).
    xml = Path(ctx.ui.dump()["path"]).read_text()
    rows = _parse_comment_rows(xml)
    if not rows:
        cmt = ctx.ui.find_by_resource_id(xml, "com.ss.android.ugc.aweme:id/eql")
        if cmt is None:
            raise EmError(
                ErrorCode.ELEMENT_NOT_FOUND,
                "comment entry not visible",
                hint="open a video detail first via `douyin open --rank N`",
            )
        ctx.input.tap_node(cmt)
        time.sleep(2)
        xml = Path(ctx.ui.dump()["path"]).read_text()
        rows = _parse_comment_rows(xml)

    target = select_comment(rows, rank=args.rank, match=args.match)

    # Tap the row's 回复 button -> opens compose targeted at that comment.
    ctx.input.tap_node(target.reply_node)
    time.sleep(1.5)

    inp = ctx.ui.find_by_resource_id(
        Path(ctx.ui.dump()["path"]).read_text(), "com.ss.android.ugc.aweme:id/eoy"
    )
    if inp is None:
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            "reply input not visible",
            hint="tapping 回复 did not open the compose box",
        )
    ctx.input.tap_node(inp)
    time.sleep(1.0)
    ctx.input.type_text(args.text)  # type_text_humanized handles CJK via ADBKeyboard
    time.sleep(1.5)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    send_btn = ctx.ui.find_by_resource_id(xml, "com.ss.android.ugc.aweme:id/es1")
    if send_btn is None:
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            "send button did not appear",
            hint="text may not have been entered; check IME with `doctor`",
        )

    if not getattr(args, "commit", False):
        ctx.input.keyevent("back")
        return {
            "dry_run": True,
            "committed": False,
            "target_index": target.index,
            "target_text": target.text,
            "text": args.text,
            "send_button_cx": send_btn["cx"],
            "send_button_cy": send_btn["cy"],
        }

    ctx.input.tap_node(send_btn)
    time.sleep(4)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    verified = args.text in xml
    ctx.governor.record("comment")
    return {
        "dry_run": False,
        "committed": True,
        "verified_visible": verified,
        "target_index": target.index,
        "text": args.text,
    }
```

> 注:抖音 reply 复用 `comment` 的 compose(`eoy` 输入 + `es1` 发送),`type_text` 内置 CJK(ADBKeyboard),与现有 douyin comment 一致。真机风险(Step 5 验):① `es1` 对「回复 compose」未经验证,不同则以 dump 为准修正;② 若 CJK 输入时 IME 切换关掉了 compose,改用 xhs reply 的「预切 ADBKeyboard + 末尾 restore」写法(见 Task 7)。

- [ ] **Step 2: 单测无回归 + verb 注册**

Run: `uv run pytest tests/unit -q` → PASS。
Run: `uv run mobilecli douyin reply --help` → 显示 `--rank/--match/--text/--commit`。

- [ ] **Step 3: 追加集成测试** — 在 `tests/integration/test_douyin_engage.py` 末尾加:

```python
@pytest.mark.integration
def test_douyin_reply_dry_run_selects_and_locates_send(serial: str):
    """Self-contained: navigate fresh, don't depend on a prior test's screen."""
    _cli("--serial", serial, "douyin", "launch")
    _cli("--serial", serial, "douyin", "search", "--keyword", os.environ.get("EM_DOUYIN_KEYWORD", "猫"))
    _cli("--serial", serial, "douyin", "open", "--rank", "1")
    payload = _cli("--serial", serial, "douyin", "reply", "--rank", "1", "--text", "test")
    assert payload["ok"] is True, payload
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["target_index"] == 1
    assert payload["data"]["send_button_cx"] > 0
```

- [ ] **Step 4: 真机跑集成(dry-run)**

Run: `EM_INTEGRATION=1 uv run pytest tests/integration/test_douyin_engage.py::test_douyin_reply_dry_run_selects_and_locates_send -q`
Expected: PASS。
> 若 dry-run 报 "send button did not appear":先 `screenshot` 确认 reply compose 已打开,再对输入文字后的界面 dump,找 `eoy` 旁的发送键 resource-id 替换 `es1`,并在 Task 8 selectors 文档记录来源。

- [ ] **Step 5: 真发验证(手动,一次)**

```bash
EM_ALLOW_COMMIT=1 uv run mobilecli --serial <S> douyin reply --rank 1 --text "说得对" --commit --pretty
```
Expected: 手机上第 1 条评论下出现你的二级回复。

- [ ] **Step 6: Commit**

```bash
git add src/mobilecli/apps/douyin.py tests/integration/test_douyin_engage.py
git commit -m "feat(douyin): reply verb(二级追评, rank/match)"
```

---

## Task 6: 小红书 `_parse_comment_rows`(堆叠 + 顶层过滤)

**Files:**
- Modify: `src/mobilecli/apps/xiaohongshu.py`(新增 import + helper)
- Test: `tests/unit/test_xhs_comments.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_xhs_comments.py
"""Offline tests for Xiaohongshu comment-row parsing -- uses fixture XML."""

from __future__ import annotations

from pathlib import Path

from mobilecli.apps.xiaohongshu import _parse_comment_rows

FIX = Path(__file__).parent.parent / "fixtures"


def _xml() -> str:
    return (FIX / "xhs-comments.xml").read_text()


def test_parses_only_toplevel_rows():
    rows = _parse_comment_rows(_xml())
    # 3 条顶层评论(子楼 subCommentLayout 内的回复被 x<180 过滤掉)
    assert len(rows) == 3
    assert [r.index for r in rows] == [1, 2, 3]


def test_row_text_is_tv_content():
    rows = _parse_comment_rows(_xml())
    assert rows[0].text.strip() == "好好看"
    assert rows[1].text.strip() == "这两套也好看"
    assert rows[2].text.strip() == "这俩也好看"


def test_reply_node_is_toplevel_time_reply_line():
    rows = _parse_comment_rows(_xml())
    n = rows[0].reply_node
    assert "回复" in n["text"]
    assert n["bounds"][0] < 180  # top-level, not indented sub-reply
    # reply line sits below its comment text
    assert n["bounds"][1] >= 797
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_xhs_comments.py -q`
Expected: FAIL — `ImportError: cannot import name '_parse_comment_rows'`

- [ ] **Step 3: 写最小实现** — 在 `xiaohongshu.py` 顶部 import 区加:

```python
from mobilecli.apps._comments import CommentRow, select_comment
from mobilecli.core.ui import find_all_by_resource_id
```

在 `back` verb 之后、`like` verb 之前加:

```python
# ----- comments (shared parse for reply) ----------------------------------------

_TOPLEVEL_X_MAX = 180  # top-level comments start x≈149; sub-replies indent to x≈215
_TV_CONTENT_ID = "com.xingin.xhs:id/tv_content"
_TIME_REPLY_ID = "com.xingin.xhs:id/newTimePoiIpTransTv"


def _parse_comment_rows(xml: str) -> list[CommentRow]:
    """Parse top-level comment rows from the scrolled note-detail comments area.

    XHS stacks per comment: tv_user_name -> tv_content -> newTimePoiIpTransTv
    ("date region 回复"). Sub-replies live in subCommentLayout, indented to
    x≈215, and are excluded (x<180). Each top-level tv_content is paired with
    the nearest top-level time/reply line below it (the 回复 affordance).
    """
    contents = [
        n for n in find_all_by_resource_id(xml, _TV_CONTENT_ID)
        if n["bounds"] and n["bounds"][0] < _TOPLEVEL_X_MAX
    ]
    replies = [
        n for n in find_all_by_resource_id(xml, _TIME_REPLY_ID)
        if n["bounds"] and n["bounds"][0] < _TOPLEVEL_X_MAX
    ]
    rows: list[CommentRow] = []
    for content in contents:
        below = [r for r in replies if r["bounds"][1] >= content["bounds"][3]]
        if not below:
            continue  # partially-scrolled last row with no reply line visible
        reply_node = min(below, key=lambda r: r["bounds"][1])
        rows.append(CommentRow(
            index=len(rows) + 1,
            text=content["text"],
            reply_node=reply_node,
            content_node=content,  # fallback tap target if 回复 span miss
        ))
    return rows
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_xhs_comments.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/mobilecli/apps/xiaohongshu.py tests/unit/test_xhs_comments.py
git commit -m "feat(xiaohongshu): _parse_comment_rows(堆叠+顶层过滤)"
```

---

## Task 7: 小红书 `reply` verb

**Files:**
- Modify: `src/mobilecli/apps/xiaohongshu.py`(新增 `reply` verb)
- Test: `tests/integration/test_xhs_reply.py`(真机,gated)

- [ ] **Step 1: 写实现** — 在 `xiaohongshu.py` 的 `comment` verb 之后、`engage` 之前加:

```python
# ----- reply (二级追评) ---------------------------------------------------------


def _scroll_to_comments(ctx: ExecContext, max_swipes: int = 5) -> list[CommentRow]:
    """Swipe up on the note detail until top-level comments come into view.

    Mirrors spec §3.4 step1: the verb ensures comments are visible (already
    there -> no-op). Returns the parsed rows from the final screen state.
    """
    rows = _parse_comment_rows(Path(ctx.ui.dump()["path"]).read_text())
    swipes = 0
    while not rows and swipes < max_swipes:
        ctx.input.swipe((540, 1800), (540, 700))
        time.sleep(1.0)
        rows = _parse_comment_rows(Path(ctx.ui.dump()["path"]).read_text())
        swipes += 1
    return rows


def _reply_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--rank", type=int, help="reply to the Nth visible comment")
    p.add_argument("--match", help="reply to first visible comment containing this text")
    p.add_argument("--text", required=True)


@app.verb("reply", add_args=_reply_args, requires_commit_flag=True)
def reply(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Reply to a comment on the current note (creates a 2nd-level reply).

    Select target by --rank N or --match "kw" (exactly one). Default = dry-run
    (locate target + send button, cancel). --commit actually sends.
    Scrolls the note detail to bring comments into view if needed.
    """
    ctx.linter.check_or_raise(args.text)
    ctx.governor.check_or_raise("comment")

    rows = _scroll_to_comments(ctx)
    if not rows:
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            "no comments found after scrolling",
            hint="open a note detail first via `xiaohongshu open --rank N`",
        )
    target = select_comment(rows, rank=args.rank, match=args.match)

    # CJK: pre-swap ADBKeyboard before opening compose; restore at the very end
    # (an IME change while compose is open dismisses it -- same as `comment`).
    needs_cjk = not args.text.isascii()
    prev_ime = _ime.current_ime(ctx.device) if needs_cjk else None
    if needs_cjk:
        _ime.set_adbkeyboard(ctx.device)
        time.sleep(0.6)

    try:
        # Tap the 回复 affordance: it's the right-end word of the time/region line
        # ("04-17 河北 回复"). Center is the date, so tap near the right edge.
        rn = target.reply_node
        ctx.input.tap_xy(rn["bounds"][2] - 40, rn["cy"])
        time.sleep(1.5)

        xml = Path(ctx.ui.dump()["path"]).read_text()
        compose = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/mContentET")
        if compose is None and target.content_node is not None:
            # Fallback: right-edge tap missed the 回复 span -> tap the comment
            # text itself (also opens the reply compose on this build).
            ctx.input.tap_node(target.content_node)
            time.sleep(1.5)
            xml = Path(ctx.ui.dump()["path"]).read_text()
            compose = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/mContentET")
        if compose is None:
            raise EmError(
                ErrorCode.ELEMENT_NOT_FOUND,
                "XHS reply compose not visible",
                hint="tapping 回复 did not open the compose box; verify tap point with screenshot",
            )

        ctx.input.tap_node(compose)
        time.sleep(1.0)
        if needs_cjk:
            ctx.device.shell(f"am broadcast -a ADB_INPUT_TEXT --es msg {shlex.quote(args.text)}")
        else:
            ctx.input.type_text(args.text)
        time.sleep(1.5)

        xml = Path(ctx.ui.dump()["path"]).read_text()
        send_btn = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/commentFuncBtnSend")
        if send_btn is None:
            raise EmError(
                ErrorCode.ELEMENT_NOT_FOUND,
                "send button did not appear",
                hint="text may not have been entered; check IME with `doctor`",
            )

        if not getattr(args, "commit", False):
            ctx.input.keyevent("back")
            return {
                "dry_run": True,
                "committed": False,
                "target_index": target.index,
                "target_text": target.text,
                "text": args.text,
                "send_button_cx": send_btn["cx"],
                "send_button_cy": send_btn["cy"],
            }

        ctx.input.tap_node(send_btn)
        time.sleep(4)
        xml = Path(ctx.ui.dump()["path"]).read_text()
        verified = args.text in xml
        ctx.governor.record("comment")
        return {
            "dry_run": False,
            "committed": True,
            "verified_visible": verified,
            "target_index": target.index,
            "text": args.text,
        }
    finally:
        if needs_cjk and prev_ime:
            _ime.restore_ime(ctx.device, prev_ime)
```

> 风险(真机定):点 `newTimePoiIpTransTv` 右端是否触发回复。若不触发,退路 = 改点该行对应的 `tv_content`(`target` 里加存 content 节点)。集成测试用 ASCII text 先验路径,再验 CJK。

- [ ] **Step 2: 单测无回归 + verb 注册**

Run: `uv run pytest tests/unit -q` → PASS。
Run: `uv run mobilecli xiaohongshu reply --help` → 显示 `--rank/--match/--text/--commit`。

- [ ] **Step 3: 写集成测试(gated)**

```python
# tests/integration/test_xhs_reply.py
"""Xiaohongshu reply integration -- EM_INTEGRATION=1 + connected device.

dry-run only (no commit). Pre-req: a note detail open with comments scrolled
into view. Set EM_XHS_KEYWORD to let the test navigate from home."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest


def _cli(*args: str) -> dict:
    r = subprocess.run(
        [sys.executable, "-m", "mobilecli", *args],
        capture_output=True, text=True, check=False,
    )
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def serial() -> str:
    r = subprocess.run(["adb", "devices"], capture_output=True, text=True, check=False)
    online = [ln.split("\t")[0].strip() for ln in r.stdout.splitlines() if "\tdevice" in ln]
    if not online:
        pytest.skip("no device connected")
    return online[0]


@pytest.mark.integration
def test_xhs_reply_dry_run_selects_and_locates_send(serial: str):
    _cli("--serial", serial, "xiaohongshu", "launch")
    _cli("--serial", serial, "xiaohongshu", "search", "--keyword", os.environ.get("EM_XHS_KEYWORD", "穿搭"))
    _cli("--serial", serial, "xiaohongshu", "open", "--rank", "1")
    # reply verb scrolls comments into view itself (no manual scroll needed)
    payload = _cli("--serial", serial, "xiaohongshu", "reply", "--rank", "1", "--text", "nice")
    assert payload["ok"] is True, payload
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["send_button_cx"] > 0
```

- [ ] **Step 4: 真机跑集成(dry-run)**

reply verb 自带滚到评论区,直接:
Run: `EM_INTEGRATION=1 uv run pytest tests/integration/test_xhs_reply.py -q`
Expected: PASS(若失败,先 `screenshot` 确认评论区可见 + 核对回复落点)。
> 小红书需登录态才能真发;dry-run 不发,定位即可。

- [ ] **Step 5: 真发验证(手动,一次,需登录)**

```bash
EM_ALLOW_COMMIT=1 uv run mobilecli --serial <S> xiaohongshu reply --rank 1 --text "好看" --commit --pretty
```
Expected: 第 1 条评论下出现二级回复(未登录会跳登录墙 → 记录为 best-effort)。

- [ ] **Step 6: Commit**

```bash
git add src/mobilecli/apps/xiaohongshu.py tests/integration/test_xhs_reply.py
git commit -m "feat(xiaohongshu): reply verb(二级追评, rank/match)"
```

---

## Task 8: 文档 — selectors.md verb 映射

**Files:**
- Modify: `research/ui-trees/douyin/00-selectors.md`(加 `like` / `reply` 映射)
- Modify: `research/ui-trees/xiaohongshu/00-selectors.md`(加 `reply` 映射)

- [ ] **Step 1: 抖音文档** — 在 `## Recommended mobilecli douyin verb mapping` 末尾加:

```markdown
### `like` — **requires login (logged-in capture)**
1. From video detail, find `resource-id=gl1` (content-desc `未点赞，喜欢<N>，按钮`).
2. dry-run: return coords. --commit: tap, re-dump, verify `未点赞`→`已点赞`.

### `reply (--rank N | --match "kw") --text T` — 二级追评
1. Open comments overlay (tap `eql`).
2. Parse rows: each top-level comment = `fco` (content-desc=full text) ∋ `xdh` (回复). Anchor on xdh, pair to enclosing fco.
3. Select by rank (Nth xdh) or match (fco content-desc contains kw).
4. Tap the row's `xdh` → compose `eoy` → type → send `es1`.
5. dry-run cancels; --commit sends + verifies.
```

- [ ] **Step 2: 小红书文档** — 在 `## Recommended mobilecli xiaohongshu verb mapping` 末尾加:

```markdown
### `reply (--rank N | --match "kw") --text T` — 二级追评 — **requires login on send**
1. Scroll comments into view on the note detail.
2. Parse rows: top-level `tv_content` (x<180) paired with nearest `newTimePoiIpTransTv` ("date region 回复") below it. Sub-replies in `subCommentLayout` (x≈215) excluded.
3. Select by rank (Nth) or match (tv_content contains kw).
4. Tap right end of the time/reply line (回复 word) → compose `mContentET` → ADBKeyboard inject → send `commentFuncBtnSend`.
5. dry-run cancels; --commit sends (login wall fires if logged out).
```

- [ ] **Step 3: Commit**

```bash
git add research/ui-trees/douyin/00-selectors.md research/ui-trees/xiaohongshu/00-selectors.md
git commit -m "docs(selectors): like + reply verb 映射"
```

---

## 收尾验证

- [ ] 全量单测:`uv run pytest tests/unit -q` → 全绿。
- [ ] lint:`uv run ruff check src tests` → 无新增告警。
- [ ] 真机集成(dry-run):`EM_INTEGRATION=1 uv run pytest tests/integration -q` → 全绿。
- [ ] 三个真发动作各手动跑一次(抖音 like、抖音 reply、小红书 reply),确认手机上真实生效。
- [ ] 更新 `营销智能体` 仓 handoff:everything-mobile 侧已补抖音 like + 两端 reply;TS 侧能力矩阵后续打开。
