# 设计:小红书 profile(登录态 + 头像/昵称)

- 日期:2026-06-01
- 状态:已与用户对齐 + 真机侦察完成,待 spec 评审
- 仓库:`everything-mobile`(`mobilecli` Python CLI)
- 关联:与同日 `publish` spec 同批;消费方「营销智能体」发布前需确认当前登录账号
- selector 事实源:`research/ui-trees/xiaohongshu/00-selectors.md`(新增「我 / profile」节)+ `22-profile-logged-in.{xml,png}`(2026-06-01 真机,已登录)

## 1. 背景与目标

新增 `xiaohongshu profile`:**探测账号登录态;已登录则读取头像 + 昵称**(及顺带可得的资料字段)。用于调用方在自动化发布/互动前确认"当前这台手机登录的是哪个账号"。

只读 verb(同 `detail`),无变更动作、无双闸、无 governor cap。

## 2. 命令签名

```
mobilecli xiaohongshu profile [--avatar-out PATH]
```

- `--avatar-out`:头像 PNG 落盘路径(可省,默认 `~/.everything-mobile/<account>-avatar.png` 或临时路径)。
- 前置状态:无(verb 自己进「我」tab)。

## 3. 架构(组件 + 放置)

### 3.1 地基:区域截图裁剪(`core/screenshot.py` 加 helper)

```python
def capture_region(device, bounds: tuple[int,int,int,int], out_path: str) -> dict:
    # screencap 全屏 PNG bytes -> Pillow 按 bounds 裁剪 -> 存 out_path
    # return {"path", "width", "height"}
```

- 依赖:新增 **Pillow**(`pyproject.toml`)。轻量标准库,后续任何"裁剪屏上元素图"都可复用(非仅 profile)。
- bounds **运行时从节点读**(分辨率相关),不硬编码。

### 3.2 profile verb 编排(`apps/xiaohongshu.py`)

1. 进「我」tab:`index_me`(972,2288)。
2. **拦截未完成草稿弹窗**(若上次有草稿会弹「继续编辑笔记吗?」):dump 若见 `btn_unfinished_draft_dialog_exit` → 点它关掉(不存草稿、不去编辑)。
3. dump。**登录态 oracle**:
   - `profile_new_page_avatar_card_nickname` 或 `iv_avatar` 存在 → `logged_in:true`,继续抽取。
   - 否则 → `logged_in:false`(登出态「我」页是登录/注册引导;亦可能跳 `com.xingin.login.*`,见 `00-selectors.md` 登录墙节)→ 直接返回 `{"logged_in": false}`。
4. 抽取文本字段(见 §4)。
5. 头像:读 `iv_avatar` 的 bounds → `core.screenshot.capture_region(bounds, avatar_out)` → 返回路径。
6. 返回 JSON。

### 3.3 返回结构

```json
{ "logged_in": true,
  "nickname": "测试昵称",
  "red_id": "test_red_id",
  "ip": "北京",
  "follow_count": 2, "fans_count": 29, "fav_count": 197,
  "bio": "测试简介一\n测试简介二\n测试简介三",
  "avatar": "/path/to/avatar.png" }
```
未登录:`{ "logged_in": false }`。

## 4. 字段 → selectors(我页 / `IndexActivityV2` 的"我"tab)

| 字段 | resource-id | 取值 | bounds(本机) |
|---|---|---|---|
| 头像 | `com.xingin.xhs:id/iv_avatar` | 裁剪图;content-desc 亦含「头像,<昵称>」 | [5,205][289,489] |
| 昵称 | `com.xingin.xhs:id/profile_new_page_avatar_card_nickname` | text | — |
| 小红书号 | `com.xingin.xhs:id/profile_new_page_avatar_card_redid` | text 去前缀「小红书号：」 | — |
| IP 属地 | `com.xingin.xhs:id/profile_new_page_avatar_card_ip` | text | — |
| 关注数 | `com.xingin.xhs:id/follow_count`(`follow_ll` desc=「2关注」) | int | — |
| 粉丝数 | `com.xingin.xhs:id/fans_count`(`fans_ll` desc=「29粉丝」) | int | — |
| 获赞与收藏 | `com.xingin.xhs:id/fav_count`(desc=「197获赞与收藏」) | int | — |
| 简介 | `com.xingin.xhs:id/userDescTv` | text(含换行) | [42,591][1038,770] |

计数兜底:`*_count` 文本拿不到时,从 `follow_ll`/`fans_ll` 的 content-desc 正则抽数字(同现有 detail 的 `_parse_count` 范式)。

## 5. v1 边界(YAGNI)

- 只读**本账号「我」页**;不做他人主页、不做粉丝/关注列表抓取、不做笔记列表。
- 不做登录/登出操作(profile 只**探测**,不改登录态)。
- 头像只裁主头像;不抓背景图 / 装扮。

## 6. 测试(TDD)

### 单测(`tests/unit/`,fixture)
- `test_xhs_profile_parse.py`:用 `22-profile-logged-in.xml` fixture → 抽出 nickname/red_id/ip/三计数/bio;计数兜底(从 `*_ll` content-desc 抽数)。
- 登录态 oracle:logged-in fixture → true;构造一个无 `iv_avatar`/nickname 的最小 xml → false。
- `capture_region`:mock screencap bytes(小 PNG)→ Pillow 裁剪尺寸正确。

### 集成(`EM_INTEGRATION=1` + 真机)
- 已登录真机:`profile` 返回 nickname=「测试昵称」、各计数、avatar PNG 落盘且非空。
- 登出态:**无法实测**(不能真登出)→ 记为风险,oracle 逻辑靠 fixture + 现有登录墙分析。

## 7. 已知风险

1. **登出态未实测**:账号当前已登录,无法真登出验证 `logged_in:false` 分支 → 靠最小 fixture + `00-selectors.md` 登录墙活动名兜底;首次遇到登出真机时复核。
2. **头像 bounds 分辨率相关**:运行时从 `iv_avatar` 节点读 bounds,**不硬编码**(本机 [5,205][289,489] 仅记录)。
3. **未完成草稿弹窗**:进「我」前可能弹 `unfinished_draft_dialog` → 必须先 `btn_unfinished_draft_dialog_exit` 关掉,否则 dump 抓到的是弹窗不是主页。(publish verb 入口同样要处理此弹窗。)
4. **Pillow 依赖**:新增 `pyproject.toml` 依赖;若不希望加,退路 = §AskUser 的"返回全截图+bounds 由调用方裁"(本设计按用户选择采用裁剪 PNG)。
5. selector 漂移:`profile_new_page_avatar_card_*` 是新捕获,跨版本可能变 → 抽取失败抛 `ELEMENT_NOT_FOUND` 带 hint。

## 8. 实施阶段(可与 publish 同 plan 或独立 plan)

1. **地基**:`core.screenshot.capture_region` + Pillow 依赖 + 单测。
2. **profile verb**:进「我」+ 草稿弹窗拦截 + 登录态 oracle + 字段抽取(纯函数 `_parse_profile(xml)` 易单测)+ 头像裁剪。
3. **集成验**:已登录真机跑通;登出分支记风险。
4. **文档**:README CLI 表加 `xiaohongshu profile`;`00-selectors.md` 补「我 / profile」节。

> profile 与 publish 都是本会话的 XHS 增量;抖音/快手的 profile 同样后续按"复制"思路各自补(我页结构不同,需各自侦察)。
