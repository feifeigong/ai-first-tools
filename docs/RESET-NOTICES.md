# Codex 重置消息提醒：公开来源与接入方案

## 2026-10-28：确认依据与状态词

Windows0.3.20 / Mac preview.23候选修正完成帖被当成预告的问题。判断使用X官方英文原文与引用、回复关系；桌面机器翻译及第三方“已完成”标签不作为确认依据。10/28的[完成帖](https://x.com/thsottiaux/status/2115330127886463244)引用[时间补充帖](https://x.com/thsottiaux/status/2115273253711409208)，后者回复[重置主帖](https://x.com/thsottiaux/status/2115273064481218829)。本次完成与明天另有好消息是两个意思，后半句不能重新变成重置预告。

| 状态 | 含义 |
| --- | --- |
| 重置确认 | Tibo已明确确认该次重置，显示确认帖的北京时间；个人到账以Codex用量为准。 |
| 等待重置 | 已发布预告，尚未到预计时间，或具体时间仍待公布。 |
| 预计已生效 | 原预计时间已过，仅为按预告推算；程序尚未取得对应确认帖，不等于已核实到账。日历格简写“预计生效”。 |
| 发放重置卡 | 发布发卡消息，和直接恢复额度分开；不会因此自动用卡。日历格简写“发重置卡”。 |
| 待核实 | 原文、关联证据或语言含义还不能可靠核对，不当作已确认，也不据此弹提醒。 |

[AIHOT的公开说明](https://aihot.news/codex-reset)区分官方确认/到账核实与预计时间推算，标明每10分钟检查一次；其未开源重置监控的完整实现，不能据页面断言所有后台判定细节。本工具不读取个人额度来确认，也不采用其按习惯推算时间或人工到账结果。当前为有界规则与官方上下文核验，不承诺任意语言自动理解或长期零遗漏。

## 2026-10-23 当前查询修复

以下规则替代下文早期“只取近期帖子、页面只展示最新一条”的实现。日历保留最近30天已获取的历史；未标日期不代表没有重置，不推测周期。

- 最新消息继续从 codex-reset.com/feed 发现，固定域名官方 oEmbed 核对。feed 的 events 只提供规范原帖编号线索，忽略运营者完成标签、观察时间和摘要解释，发帖时间按原帖编号解码并与原始时戳复核。
- 新增 [Codex Reset News 公开分页历史](https://www.codexreset-news.com/developers?lang=en)作为补查线索，固定 `/api/v1/tibo/history`、100条/页，使用 next_offset 持久翻页。读取原文，不使用其模型分类、翻译或额度观察。过期档案可以用来找旧编号，但不能授权新提醒；按官方原文重新核对。每轮最多24条历史候选，持久队列继续旧任务，不重复只检查最新12条。
- 最新候选先核对，历史失败不抹掉已核实的新消息；feed 新鲜度失败也不阻断历史查看，但不标为最新读取成功、不发提醒。历史入口和其他域名均固定，拒绝任意 URL、异常时间、错误作者、正文冲突和无进展分页。
- 短预告与明确完成措辞补齐；发放重置卡为独立 banked 类型，不与直接重置混用。官方引用完成的关联从 `cdn.syndication.twimg.com/tweet-result` 的公开嵌入 JSON 核对当前作者、ID、正文、时间及引用作者/ID，之后仍重新核对所引原文。该嵌入内部数据格式不是稳定、正式的 X 用户帖子 API 契约，失效时拒绝推断，不绕过登录或认证。
- 独立 Done 无结构关联不能单凭前后时间认定同一次重置；官方截断正文不能拿第三方尾段补成完成证据。这两种历史记录单独显示“待核实”，不计完成、不进入通知队列。完整原文检查仍保持严格，诊断报告把待核实与明确消息分开统计。
- 正常请求带明确软件 User-Agent，不使用账号、Cookie、Key、翻译或模型 API。新增读取只有匿名 GET，不触发第三方采集/翻译/刷新接口。所有重置消息不会自动改变续跑开关、额度或重置卡。

本轮最终包验证、真实匿名读取结果与仍需验收的边界见 [RESET-NOTICES-QA.md](RESET-NOTICES-QA.md)。

## 2026-10-22 调研结论

目标账号是 [Tibo（@thsottiaux）](https://x.com/thsottiaux)，即 Thibault Sottiaux。OpenAI 的[官方文章](https://openai.com/index/openai-to-acquire-ona/)列出其职务为 Core Products Lead。本轮通过 X 官方 oEmbed 对 6 条公开原帖核实，返回作者名 Tibo 和该账号链接；没有登录账号、读取 Cookie 或认证，也没有调用模型。

建议第一版使用 [codex-reset.com 公开 feed](https://codex-reset.com/api/feed)发现候选，再用 [X 官方 oEmbed](https://docs.x.com/x-for-websites/oembed-api)核对已知原帖，核对通过后才发提醒。前者是第三方社区来源，不是 X 官方发现接口，也没有已核实的服务保障。提醒只代表 Tibo 发布了消息，不代表用户的个人额度已经恢复，更不能据此触发续跑或兑换重置。

公开读取研究、通知实现及构建验证已完成，独立“续跑与重置预览”待打开给用户验收。最终 WPF 108 项、冻结记忆 9 项、冻结续跑 4 项、实际冻结进程控制 7 项及包内容检查通过；通知居中调整后重新构建并复查 WPF 与三份界面渲染，结果通过。完整证据与未验收边界见 [RESET-NOTICES-QA.md](RESET-NOTICES-QA.md)，不能将公开接口可用性或合成验证当作真实通知、个人额度、省卡或模型续跑已通过。

## 当前可用性实测

以下是 2026-10-22 08:57–09:00 UTC 左右的匿名 HTTP 读取结果，只能说明本次可用性，不能承诺长期稳定。

| 来源 | 实测结果 | 适用范围 |
| --- | --- | --- |
| `https://codex-reset.com/api/feed` | HTTP 200，JSON，`source=x-api`、`source_scope=timeline`、`stale=false`；最近一次读取的 `fetched_at=2026-10-22T08:56:12.979Z`；缓存头 `public, max-age=60` | 发现候选；采集方式为服务自己声明，不能当作本工具箱直接调用官方 API |
| `https://publish.x.com/oembed`，参数为已知原帖 URL | 6 条原帖均 HTTP 200，作者与正文一致 | 官方原文核对，不负责发现新帖 |
| 同一 oEmbed，参数为账号主页 URL | HTTP 200，只返回时间线链接和嵌入标记 | 不是可轮询的最新帖子列表 |
| `https://www.codexreset-news.com/api/v1/tibo?limit=3` | HTTP 200，但 `stale=true`，来源更新时间停在 07:04 UTC | 备用历史阅读；不能用过期快照触发新提醒 |
| `https://www.codexreset-news.com/api/v1/signals?limit=3` | HTTP 200，同样 `stale=true` | 与上一来源共用上游，不能当第二个独立核实来源 |
| `https://rsshub.app/twitter/user/thsottiaux` | HTTP 404 | 本次不可用 |
| `https://nitter.net/thsottiaux/rss` | HTTP 410 | 本次不可用 |
| `https://x.com/thsottiaux` | 网页读取工具返回 HTTP 403 | 不采用匿名主页抓取作为运行依赖 |

[Codex Reset News 的公开开发文档](https://www.codexreset-news.com/developers?lang=en)明确允许无需认证的 GET 请求，但其数据注明来自 codex-reset.com。它的分类、翻译和更新时间不能代替原帖核对。`/api/health` 的服务正常也不等于采集内容新鲜。

[X 官方用户帖子接口](https://docs.x.com/x-api/users/get-posts)需要 Bearer token；[当前官方价格](https://docs.x.com/x-api/getting-started/pricing)为按量付费。以后若由工具箱运营方集中使用官方 API，终端用户仍可不填 Key，但运营方需要自己的凭据和费用安排，本轮没有创建这些依赖。

[RSSHub 的 Twitter 路由源码](https://github.com/RSSHub/RSSHub/blob/master/lib/routes/twitter/user.ts)仍列出账号、认证令牌或第三方接口配置，不能把它当成完全无认证的官方 RSS。[Nitter 官方仓库](https://github.com/zedeus/nitter)已归档，并记录收到 X 要求停止运营的函件；不把公共 Nitter 代理作为可持续产品依赖。这里不对第三方服务的上游授权作法律保证，也不通过登录、挑战绕过或私有接口补救。

2026-10-22 09:19:26 UTC 使用当前工具箱服务代码再次匿名读取，结果 `fresh=true`、`partial=false`，核实当日主帖与回复两条预告，以及 10 月 20 日、10 月 13 日两条历史完成公告。报告位于 `artifacts/development/reset-public/public-reset-feed-check.json`。这次只使用隔离缓存验证公开读取，没有取通知或弹窗、控制续跑、读取认证或发送模型请求。

## Feed 字段与候选示例

当前顶层包含 `version`、`fetched_at`、`source`、`source_scope`、`stale`、`newest_post_at`、`signal_newest_post_at`、`profile`、`signal`、`tweets`、`radar_context`、`events` 等字段。用于发现候选的最小字段为：

```json
{
  "version": 1,
  "fetched_at": "2026-10-22T08:56:12.979Z",
  "source": "x-api",
  "source_scope": "timeline",
  "stale": false,
  "profile": {"handle": "thsottiaux", "name": "Tibo"},
  "tweets": [
    {
      "id": "2113162413008884099",
      "url": "https://x.com/thsottiaux/status/2113162413008884099",
      "text": "Lands tomorrow before 10am PST.",
      "at": "2026-10-22T06:55:54.000Z",
      "is_reply": true,
      "replying_to": "thsottiaux",
      "in_reply_to_tweet_id": "2113162277688070445",
      "conversation_id": "2113162277688070445",
      "kind": "signal"
    },
    {
      "id": "2112432076767289678",
      "url": "https://x.com/thsottiaux/status/2112432076767289678",
      "text": "Day 15/ Nevermind, we're still cooking...\nand reset. Enjoy.\nhttps://t.co/RZ9WhtI802",
      "at": "2026-10-20T06:33:48.000Z",
      "is_reply": false,
      "replying_to": null,
      "in_reply_to_tweet_id": null,
      "conversation_id": "2112432076767289678",
      "kind": "candidate"
    }
  ]
}
```

这是从实测响应摘取的字段，不是完整接口契约。`kind`、`explicit_reset_claim`、`events.type` 和 `signal.active` 都只能帮助发现，不能直接控制弹窗。实测中预告也会进入 `events.type=reset`，而明确完成措辞仍可能标为 `candidate`。接口还含第三方模型分类与账号观察结果；本工具不依赖这些判断，不调用其刷新、翻译、分类或私有接口，只读取原文与关联关系。

## 官方原文核对

向 `https://publish.x.com/oembed` 发匿名 GET，参数为：

```text
url=https://x.com/thsottiaux/status/<已验证为数字的帖子编号>
omit_script=true
hide_thread=true
```

官方文档说明该接口不需要认证，返回 JSON。单帖响应包含 `url`、`author_name`、`author_url`、`html`、`type`、`provider_name`、`cache_age`；实测作者为 Tibo、作者链接为 `https://x.com/thsottiaux`，HTML 包含正文和原帖链接。它是嵌入接口，结构和缓存可能变化，不能据此宣称实时发现或零延迟。

实现时应遵守以下核对顺序：

1. 仅接受固定作者 `thsottiaux`、数字 ID 和规范原帖链接。网络地址始终由固定域名与验证后的 ID 生成，不请求 feed 任意提供的地址。
2. 核实 oEmbed 返回作者链接的主机与账号、原帖链接中的 ID。仅兼容明确列出的 X/Twitter 官方域名，不按字符串包含判断。
3. 用 HTML 解析器取主帖段落，解码实体并合并空白；不执行脚本，不在工具箱渲染第三方原始 HTML。比较原文时允许空白、HTML 实体及末尾短链接表现差异，不能忽略改变语义的正文差异。
4. 缺少正文、文本被截断、作者或 ID 不符、正文冲突、解析失败的候选不弹窗。每条独立核对，单条旧帖失效不抹掉其他已经核实的结果；部分失败显示尚未完全核实，只允许完全核实的候选提醒。Feed 本身过期、结构错误或读取失败仍禁止所有新提醒，不把失败当“没有新消息”。
5. 回复必须连同对应父帖核对。仅依赖明确的 `in_reply_to_tweet_id`，父帖也须通过官方核对；不要按发布时间接近就猜属于同一次重置。没有足够上下文时只保留消息，不推断为重置预告。

## 语义边界与原帖样例

以下原帖均已通过官方 oEmbed 核对；分类是本次阅读原文后的解释，不是用户额度状态。

| 类型 | 原帖与上下文 | 提醒规则 |
| --- | --- | --- |
| 预告 | [10 月 22 日主帖](https://x.com/thsottiaux/status/2113162277688070445)宣布重置日；[紧随其后的本人回复](https://x.com/thsottiaux/status/2113162413008884099)补充落地时间 | 合并成一次“有新的重置预告”，不能写“额度已恢复” |
| 已宣布完成 | [10 月 20 日](https://x.com/thsottiaux/status/2112432076767289678)使用完成措辞；[10 月 13 日](https://x.com/thsottiaux/status/2109873287853707513)明确说已完成 | 可提醒“Tibo 宣布已重置”，仍不能保证当前用户到账 |
| 非重置 | [10 月 21 日要求重置的回复](https://x.com/thsottiaux/status/2112798407928713717)是向他人表达要求；[套餐内功能不消耗周额度](https://x.com/thsottiaux/status/2113029854417600834)是计费说明 | 不触发重置提醒，即使出现 reset、weekly 或 usage |

规则需要区分将来、完成、否定、假设、愿望与问句，不能只搜 reset 关键词。仅对明确的重置预告或完成措辞提醒；容量修复、额度倍增、银行式可领取重置和普通产品发布分别处理，不能合成“全员已经重置”。无法确定时不弹窗。

时间必须以原帖发布时区和上下文解释。当前展示使用本地确定性规则生成中文要点及北京时间，不调用翻译模型。10 月 22 日 06:55 UTC 在美国太平洋当地仍是 10 月 21 日晚上；直接用 UTC 日期计算 tomorrow 会错一天。原帖写 PST，按固定 UTC−8 换算为北京时间 10 月 23 日 02:00 前；美西当天仍处于夏令时，若其泛指当地时间则为 01:00 前。页面同时注明这一小时歧义；PT 按区域时区规则自动处理夏令时，PST/PDT 按明确偏移换算并检查与当地规则是否冲突。日期/时刻/时区不足、区间或多时刻不生成唯一时间，不把过了预计时间当成重置已完成。发布时间及消息更新时间也固定显示北京时区。依据见 [NIST 时区说明](https://www.nist.gov/pml/time-and-frequency-division/local-time-faqs)、[2026 夏令时规则](https://www.nist.gov/pml/time-and-frequency-division/popular-links/daylight-saving-time-dst) 和 [.NET 时区换算](https://learn.microsoft.com/en-us/dotnet/api/system.timezoneinfo.converttime)。

## 当前实现规则

正常每 5 分钟检查一次；用户手动刷新最短间隔 30 秒，超时或限流后逐步退避。响应大小、条目数量和正文长度均有限制。先验证结构、作者、时戳与新鲜度，再对少量候选请求官方 oEmbed，最后执行本地确定性分类；不调用模型 API。多个窗口或进程共用检查锁和持久记录，避免同时重复请求。

候选先按正文排除无关讨论，不信任 feed 的分类字段。公开实测曾发现无关回复的父帖并非 Tibo，旧实现会因这一条核对失败放弃整轮；现改为逐候选严格核对并隔离失败，作者、原帖 ID、正文及必要父帖检查没有放宽。部分失败保存为 `partial=true`，界面明确提示核实未完成；全局来源检查失败仍停止新提醒。

`stale=true`、采集时间缺失或明显过旧、时间异常均不发新提醒。当前以 15 分钟作为采集快照上限；该值是本工具策略，不是上游服务承诺。断网保留历史并标为未更新，恢复网络后先核对时间，不补弹大量过期消息。

本地保存原帖 ID、关联父帖、消息阶段和已提醒时间，以原帖及父帖阶段持久化去重；同一父帖下的主公告和时间补充合并，预告与后续完成分别识别。不要使用点赞数、列表顺序、采集时间或翻译变化作新消息依据。首次检查允许提醒最近 6 小时内经核对且符合规则的帖子，避免用户刚开启就漏掉当前预告；之后只补漏最近 24 小时内、尚未提醒且不早于首次提醒窗口的消息，不将整个历史列表逐条弹出。重开或多窗口不会让已经提醒过的帖子重新触发。

正常通知只需简短中文结果和“查看原帖”；来源详情注明“公开消息来自 codex-reset.com，原文经 X 核对”。提醒功能只读取这些公开消息，不更改 Agent 目录、账号、额度或任务。数据源失败只影响消息新鲜度，不影响既有自动续跑。

页面只展示最新一条消息，主帖与时间补充继续按父帖阶段合并提醒。用户明确要求关闭工具箱窗口后也收到提醒，现由隐藏通知程序承接，不增加进程管理界面。更新或卸载只请求属于当前包的程序正常退出；崩溃残留必须同时满足同包路径、锁不存在、token 未变才清理，其他包保持不动。关窗口后的真实通知体验仍需用户验收。

## 尚未验证

- 长期稳定性、真实平均采集延迟、上游采集完整性及服务持续开放承诺。
- 完整消息编辑、删除、长帖和跨帖上下文覆盖；oEmbed 本身可能缓存旧内容。
- 工具箱关闭、系统休眠恢复、多窗口与 Windows 通知去重体验。
- 真实账号是否恢复额度；本功能不读取账号验证，也不应作此承诺。

后续应以合成 feed、固定匿名帖子样例和本地 oEmbed 替身测试断网、过期、错误作者、正文不一致、父帖缺失、重复消息、预告变完成等情况；不要为测试发送模型请求或操作真实账号。

## 2026-10-23：日历展示规则

正常页面改为月历与日期详情，既有消息保留为历史。完成公告按北京时间发布日落日历，有明确时刻的预告按预计日期落日历；时间未明或两个时区解释跨不同日期时，只记录预告发布日并标待定。预告时间经过仍是历史预告，不能据此标成完成。默认优先有效的未来预告，再展示最近完成公告；最近记录按日期汇总，同一天的独立原帖仍可分别查看。

日历不是完整 X 时间线，也不表示已获取所有重置记录；无标记日期不代表当天没有重置，不根据几次公告推测固定周期或下一次日期。该改动只涉及既有缓存的本地展示，不改变抓取、去重、弹窗或自动续跑。
