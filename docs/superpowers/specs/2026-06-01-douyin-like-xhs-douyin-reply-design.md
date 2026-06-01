# 设计:抖音 like + 抖音/小红书 reply(二级评论追评)

- 日期:2026-06-01
- 状态:已与用户对齐,待 spec 评审
- 仓库:`everything-mobile`(`mobilecli` Python CLI)
- 关联:消费方是「营销智能体」桌面 app 的自动曝光链路(TS 侧后续接入)
- 参考实现:`src/mobilecli/apps/xiaohongshu.py`(like/comment/engage)、`apps/douyin.py`(comment)
- selector 事实源:`research/ui-trees/{xiaohongshu,douyin}/00-selectors.md` + 评论区 dump fixture

## 1. 背景与目标

`mobilecli` 当前真实 verb:小红书有 `like`/`comment`,抖音只有 `comment`(无 `like`),两端都**没有**「回复某条评论」的能力。本设计新增 3 个 verb,补齐抖音点赞 + 抖音/小红书的「二级评论追评」(回复已有评论,在其下生成二级回复)。

快手侧由用户在另一 session 并行补齐,不在本设计范围。

**能力增量:**

| verb | 平台 | 现状 |
|---|---|---|
| `douyin like` | 抖音 | 新增。detail 页点赞 |
| `douyin reply` | 抖音 | 新增。回复评论浮层里的某条评论 |
| `xiaohongshu reply` | 小红书 | 新增。回复评论区里的某条评论 |

小红书 `like`/`comment`、抖音 `comment` 已存在,**不改动**。

## 2. 命令签名

```
mobilecli douyin like                              [--commit]
mobilecli douyin reply       (--rank N | --match "kw") --text T  [--commit]
mobilecli xiaohongshu reply  (--rank N | --match "kw") --text T  [--commit]
```

- `like`:无新增参数。前置状态 = 已在视频 detail 页(同 `comment`,由 `open` 进入)。
- `reply`:`--rank N` 与 `--match "kw"` **二选一**(恰好提供一个);`--text` 必填。前置状态 = 已在 detail 页 / note 页。
- 全部沿用现有变更动作双闸:默认 **dry-run**;`--commit` + 环境变量 `EM_ALLOW_COMMIT=1` 才真正点击/发送。

## 3. 架构(组件 + 放置)

### 3.1 新增 `src/mobilecli/apps/_comments.py`(共享纯逻辑)

```python
@dataclass
class CommentRow:
    index: int                 # 1-based,当前可见顶层评论的序号
    text: str                  # 用于 --match 的可匹配文本(用户名 + 正文 + 元信息)
    reply_node: dict[str, Any] # 该行「回复」affordance 节点(含 bounds/cx/cy)

def select_comment(rows, *, rank=None, match=None) -> CommentRow:
    # 校验:rank/match 恰好一个 → 否则 EmError(UNKNOWN, "reply requires exactly one of --rank / --match")
    # rank 越界 / match 无命中 → EmError(ELEMENT_NOT_FOUND, ...)
```

`select_comment` 是纯函数,易单测。平台专属的 `_parse_comment_rows(xml)->list[CommentRow]` 留在各 app 文件(UI 结构不同),也是纯函数。

### 3.2 抖音 `_parse_comment_rows`(几何包含)

评论浮层结构(`research/ui-trees/douyin/06-comments-panel.xml`):
- 每条顶层评论 = 一个 `com.ss.android.ugc.aweme:id/fco` 容器,其 **`content-desc` = 整条评论全文**(`用户名,正文,时间, · 地区,回复 按钮,`)→ 直接作为 `CommentRow.text`。
- 回复键 = 该 fco 子树内的 `com.ss.android.ugc.aweme:id/xdh`(text="回复",clickable)。
- 「展开N条回复」(`id/4rg`,content-desc `展开N条回复，按钮`)是子楼展开器 → **忽略**,不作为目标。

**配对方式:几何包含**——枚举所有 `xdh`,对每个 xdh 找包含它中心点的 `fco`,取该 fco 的 content-desc 作 text。**不靠下标对齐**:末行常被 RecyclerView 底边裁掉,fco 在但 xdh 缺(实测 fixture 4 个 fco / 3 个 xdh)。以 xdh 为准保证目标可点。

### 3.3 小红书 `_parse_comment_rows`(堆叠 TextView + 顶层过滤)

评论区结构(`research/ui-trees/xiaohongshu/05-comments-area.xml`,同 `NoteDetailActivity` 滚动):
- 每条评论纵向堆叠:`tv_user_name` → `tv_content`(正文)→ `newTimePoiIpTransTv`("日期 地区 回复",**回复 affordance 在文字右端**)。
- 子楼在 `subCommentLayout` 内,缩进 x≈215;顶层 x≈149。→ 以 `bounds.x1 < 180` 过滤,只取顶层。
- `CommentRow.text` = 顶层 `tv_content` 文本;`reply_node` = 其下方(y 紧邻、x≈149)的 `newTimePoiIpTransTv`。

### 3.4 verb 编排(reply,两端同构)

1. 确保评论区可见(抖音:detail 页点评论图标 `eql` 打开浮层;小红书:detail 页向下滚到评论区 / 已在则跳过)。
2. `dump` → `_parse_comment_rows(xml)` → `select_comment(rows, rank, match)`。
3. 点选中行的 `reply_node` → 打开 compose(预置「回复 @某人:」)。
4. 输入 `--text`(CJK 走 ADBKeyboard `ADB_INPUT_TEXT` broadcast,套现有 `comment` 的 IME 处理:CJK 时先切 ADBKeyboard、末尾再恢复,避免输入法切换关掉 compose)。
5. `dump` 找发送键(抖音:输入后动态出现,沿用 `comment` 套路;小红书:`commentFuncBtnSend`)。
6. **dry-run**(无 `--commit`):返回选中目标 + 发送键坐标,`back` 退出,不发送。
7. **commit**:`linter.check_or_raise(text)` → `governor.check_or_raise("comment")` → 点发送 → `dump` best-effort 校验 → `governor.record("comment")`。
8. reply 复用 `comment` 的日 cap(`governor` key = `"comment"`)。

### 3.5 抖音 `like` verb

照搬小红书 `like`:detail 页 dump → `com.ss.android.ugc.aweme:id/gl1`(content-desc `未点赞，喜欢<N>，按钮` / `已点赞…`)→ `governor.check_or_raise("like")` → dry-run 返回坐标 / commit 点击 + 重新 dump 校验 `未点赞`→`已点赞` 翻转 → `governor.record("like")`。`daily_caps["like"]=200` 已存在,无需改。

## 4. lint / governor / 双闸

- `reply` 的 `--text` 过 `linter.check_or_raise`(同 comment)。
- governor:`like`→key `"like"`,`reply`→复用 key `"comment"`(回复也是评论行为,共享日 cap)。
- 双闸不变:`requires_commit_flag=True` + cli 层 `EM_ALLOW_COMMIT=1`。

## 5. 产品集成约定(约束 TS 侧,非本仓)

「营销智能体」桌面 app 调这些 verb 时:

- **永远真实发出**:一律带 `--commit` + `EM_ALLOW_COMMIT=1`。
- **产品内不暴露任何 dry-run 开关 / 路径**——用户点了就是真点赞、真评论、真回复。
- dry-run 只存在于 mobilecli CLI 自身与本仓集成测试中,不进产品 UX。

(此约定写给后续 TS 集成阶段;本仓的 CLI 仍保留 dry-run 默认。)

## 6. v1 边界(YAGNI)

- reply 只回**顶层评论**;「展开N条回复」的子楼不进列表、不回。
- `--rank`/`--match` 只在**当前可见**评论中选;翻页加载更多评论本轮不做(TS 侧后续可加 scroll/翻页编排)。
- 不做 reply 的复合 verb(类似 `engage`);粒度 verb 由 TS 侧编排。

## 7. 测试(TDD)

### 单测(`tests/unit/`,纯函数,不连真机)
- `test_comments_select.py`:`select_comment` 的 rank 命中 / rank 越界 / match 命中 / match 无命中 / rank+match 同给 / 都不给 → 各分支(含 EmError code)。
- `test_douyin_comments.py`:用 `06-comments-panel.xml` fixture → `_parse_comment_rows` 抽出 3 行,text 含对应用户名/正文,reply_node 坐标落在对应 fco 内。
- `test_xhs_comments.py`:用 `05-comments-area.xml` fixture → 只抽顶层行(排除 subCommentLayout),text=tv_content,reply_node=newTimePoiIpTransTv。
- 既有 `tests/unit/test_xml_parse.py` 范式参照。

### 集成(`EM_INTEGRATION=1` + 真机,标 `@pytest.mark.integration`)
- 真机已连(Pixel 10 Pro)。逐 verb:dry-run 定位通过 → commit 真发。
- 抖音 like:dry-run 出坐标 → commit 后 `未点赞`→`已点赞`。
- reply(两端):dry-run 选中正确行 + 出发送坐标 → commit 后 best-effort 校验回复可见。

## 8. 已知风险(真机阶段定)

1. **小红书回复落点**:`newTimePoiIpTransTv` 文字右端是「回复」,节点中心是日期。需真机验证点右端能否触发;退路 = 点 `tv_content` 看是否打开针对该评论的 compose。集成测试里定。
2. **抖音发送键动态出现**:输入文字后才出现,同 `comment` —— type 后必须重新 dump 再找发送键。
3. **抖音首评论风控**:可能弹验证码/设备校验 → commit 后校验做 best-effort,记录但不崩。
4. **reply 成功判定**:回复落在子楼内,发送后顶层 dump 未必可见 → 校验 best-effort(`verified_visible` 字段可为 false),不因校验失败判 verb 失败。
5. **selector 漂移**:抖音 rid 混淆三字符(`fco`/`xdh`/`gl1`),跨版本可能变 → 解析失败抛 `ELEMENT_NOT_FOUND` 带 hint「UI 可能已变,跑 dump 检查」。

## 9. 实施阶段(单 plan,TDD)

1. **共享底座**:`apps/_comments.py`(`CommentRow` + `select_comment`)+ 单测。
2. **抖音 like**:verb + 集成验。
3. **抖音 reply**:`_parse_comment_rows`(fco∋xdh)+ 单测(fixture)→ verb 编排 → 集成验。
4. **小红书 reply**:`_parse_comment_rows`(堆叠+顶层过滤)+ 单测(fixture)→ verb 编排 → 集成验。
5. **文档**:更新 `00-selectors.md` 的 reply/like verb 映射 + 能力说明。

> 注:everything-mobile 跑通后,「营销智能体」TS 侧的能力矩阵(`mobile/capabilities.ts`)再把抖音 like / 两端 reply 打开并接驱动 —— 那是另一仓的后续工作,见 `营销智能体` handoff。
