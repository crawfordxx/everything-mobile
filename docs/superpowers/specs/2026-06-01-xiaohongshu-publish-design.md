# 设计:发布能力地基 + 小红书 publish(图文 / 视频)

- 日期:2026-06-01
- 状态:已与用户对齐 + 真机侦察完成,待 spec 评审
- 仓库:`everything-mobile`(`mobilecli` Python CLI)
- 参考实现:`src/mobilecli/apps/xiaohongshu.py`(like/comment/engage)、`plugin/ctx.py`(ExecContext)
- selector 事实源:`research/ui-trees/xiaohongshu/00-selectors-publish.md`(2026-06-01 真机,Pixel 10 Pro / Android 16,**已登录**,端到端走通视频发布含自定义封面)

## 1. 背景与目标

`mobilecli` 现有 verb 全是**浏览/互动**(launch/search/open/detail/like/comment/reply),三端都**没有发布能力**。用户要给抖音/快手/小红书加「发布图文和视频(封面/标题/正文/话题)」。

按对齐结论分阶段:**先做跨端复用的地基 + 小红书单端垂直切片跑通,再复制到抖音/快手**(各自独立 spec/plan 周期)。本设计只覆盖:

1. **发布地基**(跨端复用):`ExecContext` 新增媒体推送原语 `ctx.media.push_to_gallery(...)`。
2. **小红书 `publish` verb**:图文(多图)+ 视频,支持标题 / 正文 / 话题 #tag / 封面 / 笔记内容声明。

抖音、快手的 publish **不在本设计范围**(待 XHS 验证模式后复制)。

**能力增量:**

| 项 | 位置 | 现状 |
|---|---|---|
| `ctx.media.push_to_gallery` | `plugin/ctx.py`(新 `MediaModule`) | 新增。push + 媒体扫描 + MediaStore 回查 |
| `xiaohongshu publish` | `apps/xiaohongshu.py` | 新增。图文/视频发布 |

## 2. 命令签名

```
mobilecli xiaohongshu publish \
    --media PATH [PATH ...] \            # 图文: 多张图; 视频: 单个 mp4/mov
    --title "标题" \
    --body  "正文" \
    [--tags "话题1,话题2"] \              # 可省;插入正式话题锚点
    [--cover N | --cover PATH] \         # 可省;见 §3.5
    [--declare ai|original|repost|fiction|marketing|opinion|none] \  # 可省,默认 none
    [--commit]
```

- **自动判型(按扩展名)**:全图片 → 图文流(按给定顺序);恰好 1 个视频 → 视频流;混合 / 多视频 → `EmError(INVALID_ARG)`。
- 沿用变更动作双闸:默认 **dry-run**;`--commit` + `EM_ALLOW_COMMIT=1` 才真正点「发布笔记」。
- 前置状态:无(verb 自己从首页 `index_post` 进入,内部 `_ensure_home` 思路同 douyin)。

## 3. 架构(组件 + 放置)

### 3.1 地基:`MediaModule`(`plugin/ctx.py`,挂 `ctx.media`)

与 `InputModule`/`UiModule` 同级,`ExecContext.build` 里装配:

```python
@dataclass
class MediaModule:
    device: Device
    def push_to_gallery(self, local_paths: list[str], subdir: str = "em-publish") -> dict:
        # 1. 校验每个 local:存在 + 扩展名白名单(.jpg/.jpeg/.png/.webp/.mp4/.mov)→ 否则 INVALID_ARG
        # 2. device.push(local, /sdcard/DCIM/<subdir>/<name>)   (复用 Layer1 Device.push)
        # 3. am broadcast MEDIA_SCANNER_SCAN_FILE -d file://<remote>  (逐文件)
        # 4. content query 回查 MediaStore 确认索引;查不到 → MEDIA_NOT_INDEXED
        # return {"pushed":[{"local","remote","indexed":True}], "count":N}
```

- 远端路径由库构造(不含用户输入),local 仅做存在/扩展名校验,杜绝注入。
- **dry-run 也会推素材**(方案 1 特性:dry-run 一路驱动到发布键前)。
- 放 `ctx.media` 而非让插件直接 `ctx.device.push`:三端复用同一套「推+扫+回查」,且保持插件不直接碰 Layer 1 的约定。
- 去索引清理(`content delete`)v1 不做,记入 §10 未来工作。

### 3.2 publish verb 编排(`apps/xiaohongshu.py`)

公共骨架(图文/视频共用后半段),selector 见 `00-selectors-publish.md`:

1. **校验 + lint**:判型;`linter.check_or_raise` 分别过 `title` / `body` / 每个 `tag`;`--media` 文件存在性。
2. **推素材**:`ctx.media.push_to_gallery(media)`(图文多张 / 视频单个;若 `--cover PATH` 一并推)。
3. **进相册**:首页 `index_post`(540,2288)→ 面板 `rlFirst` → `CapaAlbumActivity`。
   - **权限检测**:dump 若含「无法访问相册」/「去开启权限」→ `EmError(PERMISSION_REQUIRED, hint=授予 READ_MEDIA_IMAGES/VIDEO)`。
4. **选素材**:点各素材 `selectableLayout`(选择圈;图文按封面规则定顺序,见 §3.5)→ `bottomGoNext`。
5. **视频专属**:`VideoEditActivityV3` → `capa_light_edit_next`(下一步)→ 编辑页。(图文直达,跳过本步)
6. **进编辑页** `CapaPostNotePlatformActivity`:取消位置弹窗(`text_refuse`)。
7. **填标题**:点 `editTitle` → ADBKeyboard 输入 → 回查 `text` 落地。
8. **填正文**:点 `postNoteEditContentView` → ADBKeyboard 输入 → 回查。
9. **话题**(若 `--tags`):逐个 `addTopicView`(#)→ 输 tag → `topicList` 首行 `tvTopicName` → 插入 `#tag ` 锚点;首行无命中则降级(保留 `#tag ` 文本,返回标 `tag_linked:false`)。
10. **封面**(见 §3.5)。
11. **声明**(若 `--declare`≠none):`declareTv` → RN 页按文本点选项 → 返回。
12. **定位发布键**:收键盘(back)→ `capaBigPostBtn`("发布笔记")。
13. **dry-run**:截图 + 返回(见 §3.4),`back`/`force_stop` 放弃草稿。**commit**:`governor.check_or_raise("publish")` → 点 `capaBigPostBtn` → 等待 → best-effort 校验(回首页 / 出现成功提示)→ `governor.record("publish")`。

### 3.3 CJK 输入(复用 reply/comment 套路)

ADBKeyboard `ADB_INPUT_TEXT` broadcast:CJK 时**先切 ADBKeyboard、末尾恢复原 IME**(避免输入法切换关掉编辑页);broadcast 偶发 Binder 异常 → **输入后回查 EditText `text`,失败重试一次**(真机实测必要)。

### 3.4 返回结构

dry-run(默认):
```json
{ "dry_run": true, "committed": false, "media_type": "image|video",
  "pushed": [{"local","remote","indexed":true}],
  "title": "...", "body_len": 123, "tags": ["..."], "tags_linked": [true,false],
  "cover": "default | index:2 | path:/.../c.jpg", "declare": "ai|none",
  "publish_button_cx": 693, "publish_button_cy": 2223,
  "screenshot": "/tmp/xhs-publish-preview.png",
  "steps": ["pushed N media","opened composer","filled title","...","reached 发布笔记"] }
```
commit:`{dry_run:false, committed:true, verified_published:bool, ...}`。

### 3.5 封面语义(v1 明确规则,避开未侦察 UI)

- **图文**:封面 = 首图(XHS 默认)。`--cover N`(1-based)= 让第 N 张 `--media` 图当封面 → **选素材时先点第 N 张选择圈**(选中顺序=展示顺序,首张即封面),其余按序补。默认 N=1。图文不接受 `--cover PATH`(封面必须是帖内图)。
- **视频**:默认 = 系统首帧。`--cover PATH` = 上传自定义封面图(已真机验证完整链路):`bottomEditCoverAreaV2` → `album_cover_layout`(+相册)→ `MaterialSelectActivity` 点 `thumbnailIv` → `btnDone` → `ImageEditActivity3` → `rightTv`(完成)。视频不接受 `--cover N`。
- 视频"帧滑块选封面"、图文"设置封面"专用 UI v1 **不做**(无需求 / 无稳定选择器)。

## 4. lint / governor / 双闸

- **lint**:`title` / `body` / 每个 `tag` 分别 `linter.check_or_raise`(命中引流词 → `CONTENT_BANNED`,定位到具体字段)。`ContentLinter` 类不改。
- **governor**:新增动作类 `"publish"`;`xiaohongshu.daily_caps` 加 `{"publish": 3}`(来源 `docs/anti-risk-control.md` Notes posted ≤3/day,line 154/453)。commit 成功 `record("publish")`。
- **双闸**:`requires_commit_flag=True` + cli 层 `EM_ALLOW_COMMIT=1`(已有机制)。
- 模板 7 天去重(anti-risk-control.md line 290-293)v1 **不做**,记 §10。

## 5. Android 16 前置与弹窗

- **媒体权限前置**:小红书发布相册需完整 `READ_MEDIA_IMAGES`/`READ_MEDIA_VIDEO`。受限/无权限 → 相册显示「无法访问相册/去开启权限」。verb 检测此态 → `PERMISSION_REQUIRED`(hint 给授权命令)。**verb 不自动 `pm grant`**(静默改系统权限太侵入;授权是用户一次性设置,可写进 doctor / README)。
- **位置信息弹窗**:进编辑页首次弹「申请相册位置信息」→ 点 `text_refuse`(取消)。

## 6. v1 边界(YAGNI)

- 字段只做:标题、正文、话题、封面、笔记内容声明。**不做** @提及 / 标记地点 / 可见性 / 定时发布 / 添加组件 / 高级选项。
- 话题只取**搜索首行**;不做多候选选择 / 新建话题。
- 封面规则见 §3.5,不做帧滑块 / 图文设置封面 UI。
- 只做单条 publish,不做批量 / 复合 verb。
- 抖音、快手 publish 不在本设计(后续各自 spec)。

## 7. 测试(TDD)

### 单测(`tests/unit/`,纯函数 / fixture,不连真机)
- `test_media_push.py`:`push_to_gallery` 的扩展名白名单 / 文件不存在 → `INVALID_ARG`;remote 路径构造正确(mock `device.push`/`shell`);回查未命中 → `MEDIA_NOT_INDEXED`。
- `test_xhs_publish_args.py`:判型(全图→image / 单视频→video / 混合→INVALID_ARG);`--cover` 与判型的合法组合(图文 N / 视频 PATH;非法组合报错);`--declare` 取值校验。
- 话题/封面编排里的纯逻辑(选中顺序计算、tag 解析)抽纯函数单测。

### 集成(`EM_INTEGRATION=1` + 真机,`@pytest.mark.integration`)
- 真机已连(Pixel 10 Pro, Android 16, 已登录, READ_MEDIA 已授)。
- 图文 dry-run:推 2 图 → 走到 `capa_light_edit_next` 不存在(图文直达)→ 编辑页填齐 → 出 `capaBigPostBtn` 坐标 + 截图。
- 视频 dry-run:推 `原素材.mp4` → 视频编辑页 → 编辑页 → 自定义封面(`--cover PATH`)链路 → 出发布坐标 + 截图。
- commit:**用户显式授权后**单独验一条(避免污染真实账号);默认集成测试只跑 dry-run。

## 8. 已知风险

1. **图文封面/多图编辑页未单独侦察**:本轮视频流全通,图文共用编辑页(标题/正文/话题/发布选择器一致),但「图文选完是否直达编辑页」「图文封面=首图」需实现前补一次图文真机 dry-run(实施阶段第 1 步)。
2. **ADBKeyboard 偶发失败**:`#测试` 那次 broadcast 报 Binder 异常未落地 → 每次输入后必须回查 `text`,失败重试。
3. **发布键双态**:键盘开/关分别是 `capaTopPostBtn`/`capaBigPostBtn` → 定位前先收键盘统一到 `capaBigPostBtn`。
4. **声明页是 RN**:无 resource-id,靠 `find_by_text` 点行;确认交互(完成键/自动应用)实施期定。
5. **selector 漂移**:XHS 多为语义 id(较稳),但 capa.* 发布链路是新捕获,跨版本可能变 → 解析失败抛 `ELEMENT_NOT_FOUND` 带 hint「跑 dump 对照 00-selectors-publish.md」。
6. **commit 成功判定**:发布后跳转/风控不定 → best-effort 校验,`verified_published` 可 false,不因校验失败误判 verb 崩溃。
7. **风控**:发布是高权重动作(日 cap 仅 3);新号前 3 天 0 发(governor 只做计数,养号节奏由调用方遵守 anti-risk-control.md)。

## 9. 实施阶段(单 plan,TDD)

1. **图文流补侦察**:真机走一遍图文(多图)dry-run,确认直达编辑页 + 图文封面=首图,补 `00-selectors-publish.md`。
2. **地基**:`MediaModule.push_to_gallery` + `ExecContext` 装配 + 单测。
3. **publish 骨架**:判型 / 参数校验 / 返回结构 + 单测(纯逻辑)。
4. **编辑页填充**:标题/正文/话题编排(共用)→ 视频前段(编辑页跳转)/ 图文前段(直达)。
5. **封面**:图文首图规则 + 视频 `--cover PATH` 链路。
6. **声明 `--declare`** + 弹窗/权限检测。
7. **dry-run/commit** 双闸 + governor `publish` cap + lint 接入 → 集成验(dry-run 全程;commit 用户授权后单验)。
8. **文档**:README CLI 表加 `xiaohongshu publish`;`00-selectors-publish.md` 补图文。

> 注:XHS publish 跑通并验证模式后,抖音 / 快手 publish 各自开 spec/plan 复制(发布 UI 完全不同,需各自真机侦察)。
