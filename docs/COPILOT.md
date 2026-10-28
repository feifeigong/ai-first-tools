# Copilot Desktop 对话搬家

## 当前使用说明（2026-10-28）

Windows v0.3.20 与 Mac preview.23 已包含两种搬家方式：

| 方式 | 在 Copilot 中的结果 |
| --- | --- |
| 完整对话迁移 | 新增 Desktop Chats 历史副本，旧消息按 Copilot 的显示方式呈现。 |
| 智能省额度迁移 | 新增独立资料项目与「原名称（智能搬家）」对话，完整旧记录留在工具箱本机资料区供按需查找。 |

智能搬家不用选择已有工作目录或合并项目配置；每条分别保存，重复搬入会复用可核实的入口并保留后续聊天。完成后请求打开对话，用户发送下一步要求后才产生回复。操作与保护范围见[智能搬家指南](SMART-MIGRATION.md)。

Windows 已有受保护的列表刷新；任务或未发送内容存在时先保留。Mac 仅尝试可核实的明确刷新命令，已登录 Copilot 的真实菜单与侧栏仍待[真机接续](MACOS-NEXT-VALIDATION.md)，不能将原生合成检查写成全部真实客户端已验收。需要手动重开时，先完成任务并保存草稿，再正常退出和打开。

来源只读取桌面端已登记的正式记录，终端独有目录和 VS Code 自身聊天不混入。这两种搬家都适配已知本机格式，**不是 GitHub 官方的跨软件历史导入 API**；不改表结构、不迁移登录或模型权限，未知格式停止操作。下载与实际运行包验收见[首页](../README.md)、[Windows QA](UPDATER-QA.md)与[Mac QA](MACOS-QA.md)。

## 历史适配与验证记录

以下保留各版本的实现和验证过程。旧版本的手动刷新说明、旧格式及当时发布状态不代表当前全部行为；当前操作以本页开头及智能搬家指南为准。

2026-10-18 [Windows v0.3.15](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.3.15) 与 [Mac preview.18](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.18) 已发布，原生构建和全部资产独立下载核验通过。该轮修正导入内容的显示语义。旧 v1 将图片 Base64、工具调用和工具结果逐块串成普通助手正文，导致编码刷屏、JSON 日志连在正常回答前面。v2 将同一消息的普通文字合并、原始角色和时间保留；用户图片写入原生 `user.message.attachments` 的内嵌图片字段；思考仍用原生 reasoningText；原工具、系统说明和其他历史信息归入默认折叠的 `imported_history` 归档操作，不登记原工具名称或权限、不重新执行。每个归档操作均已完整结束，成功仅表示历史保存成功，不代表来源工具执行成功。完整源文档另保存在新副本的 `.ai-first-source.json`，逐字段回读验证，不出现在正常聊天正文中。

v2 去重允许旧格式记录再复制一次，源和旧副本都保留；新的本机登记时间取本次复制时间，便于在列表顶部找到，消息时间仍保留来源值。Windows Desktop 1.1.30 的合成图片、连续两轮问答和默认折叠已通过实际窗口验收。另已复现：官方 Recent 链接只导航页面，并不能保证重新加载已缓存的侧栏；旧记录可能可见，而刚搬入的记录点开后返回 New。结果页明确提示 Copilot 已开着时在 Windows 按 F5 刷新；Mac 在任务结束后完全退出 Copilot 再打开，不再把打开请求称作刷新成功。此前 v0.3.14 的“自动刷新”验收范围不充分，不能据此保证所有新导入立即可见。

上轮 v0.3.14 / preview.17 增加官方列表导航，但只对已有副本验证了打开，遗漏新写入记录的侧栏缓存。该导航不能视为可靠的自动刷新；当前提示和上述 v2 实际窗口检查已修正这一结论。

当前流程在每批完成后请求官方本机 `ghapp://chats` → `ghapp://recent` 导航，并提供「在 Copilot 中查看」和失败重试。已搬过记录仍有列表入口。这个入口不按编号直接打开聊天：`ghapp://sessions/<编号>` 在该 Desktop 版本明确拒绝普通 Chats。官方入口参见 [GitHub 深链接文档](https://docs.github.com/en/copilot/how-tos/github-copilot-app/open-with-deep-links)。缓存仍在时按前述客户端步骤刷新；Mac 共用导航但未作 Desktop 真机显示验收。

Windows 搬入与列表修正版已公开 [v0.3.13](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.3.13)，构建与独立下载核验通过。Mac 搬入与列表修正版已公开 [preview.15](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.15)，两架构构建与全部资产独立下载核验通过；下文早期版本保留为历史。

已随 [Windows v0.3.10](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.3.10)、[Mac preview.13](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.13) 公开。已有支持一键更新的版本可检查更新；更早版本下载完整安装包。构建与独立资产核验见 [Windows QA](UPDATER-QA.md)、[Mac QA](MACOS-QA.md)。

当前支持 GitHub Copilot 独立桌面 App 的本机历史搬出和搬入：在「对话搬家」中选择 GitHub Copilot，按标题或文件夹搜索、勾选记录、选择现有目标和文件夹。支持刷新重新发现记录。搬入后登记到 Desktop 的 Chats（聊天）列表。VS Code 自身的 chatSessions 不在本轮范围。

## 来源和识别

Windows 和 Mac 都读取用户目录下 `.copilot/session-state/<会话编号>/events.jsonl`。只读取这一层已知会话路径，不扫描电脑，不读取 Cookie、登录配置、凭据、工作文件或附件，也不启动 Copilot、SDK 服务或模型。

Desktop 与 CLI 共用上述存储，不能把所有 `session-state` 文件夹都当成桌面聊天。列表只枚举 `data.db/sessions` 已登记且未归档、未删除、非临时占位的桌面会话；命令行独有记录、未登记目录不再混入。只查询白名单会话字段以及工作区/项目的名称与位置，不读取认证、账户或配置内容。初始化过 Desktop 才显示入口，只有 CLI 不算安装 Desktop。

普通聊天统一归入「聊天」，不把 `.copilot/chats/…/file-c-users-…` 内部沙箱目录当作项目。项目会话用 `workspaces/projects` 的登记名称和路径分组。只有索引、没有本机正文的正式会话仍显示为不可搬运；临时占位和孤立空目录不会凑数。搬运前重新检查归档、删除及索引成员关系，未知结构或占用直接报错，不回退到混列共享目录。

2026-10-16 用户截图中的「Image-text alignment fix」与 Desktop 登记对应；原界面的 19 条包含共享存储中其他客户端的会话和无正文孤立目录，不能代表 Desktop 的 19 条聊天。截图中的内部路径编码不是项目名。当前修订把列表来源收紧为 Desktop 登记；运行中的新会话数量仍可随用户使用改变，不固定为某个数字。

## 搬入 Copilot Desktop

在来源（包括 ChatGPT 普通聊天、本机 Work/Codex）选择已有完整正文的记录，目标选 GitHub Copilot，选择工作文件夹后确认。每条创建一个新的 UUID 聊天副本并登记为 `general_chat`，位于 Desktop 的 Chats，而非自动新建项目或 worktree。Windows v0.3.16 完成后自动刷新已识别的 Copilot Desktop 窗口并打开会话列表，侧栏同步重读。正在执行任务或编辑未发送内容时保留它们，处理完后点「在 Copilot 中查看」重试；窗口身份/草稿无法核实则不发送刷新键。Mac 仍需在任务结束后完全退出 Copilot 再打开。官方深链只导航，不会使侧栏缓存失效。

这是对本机格式的适配，不是 GitHub 官方提供的跨软件历史导入 API。先检查会话表字段和必填项；格式变化、数据库占用、未知正文块时停止。消息转换为版本 1 的连续事件，搬家格式为 v2：原用户/助手角色与完整文字、时间保留；思考通过 `assistant.message.reasoningText` 保留，因为原生恢复会过滤独立 `assistant.reasoning` 事件。用户内嵌图片写为原生 blob 附件；工具调用/结果和系统说明放入已完成且默认折叠的历史归档。外部附件文件和原项目环境不迁移，不获取任意本机路径或网络图片。

写入新目录并在同一 SQLite 事务内登记、比较完整消息后提交；失败只撤销本次新行和仍与本次写入一致的文件，已有行及目录不覆盖。不复制认证、不创建自动批准或远程权限，不启动 Copilot 或模型。SQLite 写入授权只允许本次新增会话，并识别原生的条件 agent 触发器；未知触发器不能修改其他表或额外插入会话。格式版本参与去重。

## 转换和完整性

适配 `session.start` 的版本 1 事件：用户消息、助手消息、完整思考、标题/工作目录/模型变化、工具请求与结果。通过 Python 转为现有 Simple 中间格式，沿用已有 txcript 导入、登记、回读及去重流程，未修改 Rust 引擎。

- 逐行读取，不把整个事件文件拼成单个字符串；不截断长正文。重复的相同事件只计一次，同编号不同内容拒绝搬运。
- 完整事件与流式增量分开，忽略临时事件、消息增量、工具进度以及计费、hook、压缩等生命周期日志；压缩摘要不会替换已有完整历史。
- `assistant.message.toolRequests` 和对应的 `tool.execution_start` 不生成两次调用；工具返回保留普通输出、详细输出、结构化输出和错误。
- 缺少返回的调用、没有对应调用的结果、交错的子任务记录作为明确标注的历史文字保留，不编造返回、不当成待执行请求。冲突的调用编号停止搬运。
- 读取期间文件变化、JSON 不完整、未知正文结构、会话版本或编号不匹配时，保留列表提示且禁用搬运；不会忽略坏行后导入残缺记录。目录跳转和会话文件符号链接会被拒绝。
- 含截断、快照撤回或清空上下文事件的会话暂时拒绝搬运，避免把已撤回的分支当作当前对话；后续需要单独适配其恢复协议。
- 列表可搬运不代替最终检查：点击搬运后会重新读取源记录并检查索引。目标仍保留其现有格式校验、备份、回读和去重要求。

只搬对话历史及已在来源正文内嵌的图片，不复制外部文件、登录状态、工具权限或原工作环境。目标原生客户端是否显示、是否能继续发送下一轮，需要分别验收，不能以生成文件或回读通过代替。

读取器逐字保留消息正文。目标适配仍遵循原有格式，例如 WorkBuddy 的用户消息回读会去掉正文首尾空白；不承诺所有目标的排版字节完全一致。

## 开发验证

`python -m unittest test_copilot -v` 使用隔离目录和合成事件。覆盖 Windows/Mac 路径、桌面/共享来源区分、长正文、工具配对、中断调用、子任务交错、损坏与变化、未知结构、归档删除、仅云端索引、刷新和可搬入目标。引擎存在时额外实际搬入 Cursor、Codex、本机 Work、Claude Code、WorkBuddy 国内/海外版并回读，验证源文件字节不变及重复搬运。

`test_import_ui` 新增 Copilot 搜索、选择、刷新、桌面标记、损坏记录禁选、ChatGPT → Copilot 文件夹选择/确认/结果检查；`test_agent_icons` 校验随包原版图标和来源摘要。Windows 检查、Windows 打包和两种 Mac 架构的 CI 已纳入上述测试。CI 结果和安装包状态以实际运行报告为准；未对用户的真实 Copilot 数据或付费模型续聊作自动验收。

`test_copilot_import` 覆盖 125 轮完整正文、Desktop 登记、工具历史说明、ChatGPT 导出接线及去重、未知结构/触发器、失败回滚和已有目录保护。`test_copilot_native` 在独立空账户目录启动校验值固定的官方 Copilot 1.0.98 测试组件，完整分页读取全部事件，禁止修复地恢复会话，再逐字段比较所有原始事件，包括思考和长工具说明。请求白名单不含发送消息、登录、工具执行；测试组件不打包给用户。Windows、两种 Mac 架构均执行该原生检查。当前依据 Desktop 1.1.29 的索引形状，其他版本需通过同样的结构检查。

原生历史读取和严格恢复不等于已在用户 Desktop 上逐条人工滚动或发送付费下一轮。v2 在 Windows 已安装的 Copilot 1.1.30 中用独立合成图片、两轮问答及折叠工具过程验证；只撤销这次自建的两条测试行及目录，未修改用户原记录。没有升级或重开用户工具箱。Mac Desktop 界面与在线模型下一轮未验收；实际构建与发布验收见两份 QA。

图标提取自已安装 GitHub Copilot App 的程序资源，未重画、未改色，随软件打包，运行时不联网获取。资源来源与 SHA-256 见 `dialog-mover/ui/assets/agents/sources.json`。

## 依据

- [GitHub：Copilot 会话数据](https://docs.github.com/en/copilot/concepts/security-governance-and-network-settings/session-data)：CLI 和独立 App 的共享本机记录、会话索引和云端范围。
- [GitHub Copilot SDK 事件定义](https://github.com/github/copilot-sdk/blob/main/python/copilot/generated/session_events.py)：事件与字段的公开定义；本适配不依赖或运行 SDK。
- [GitHub App #2309](https://github.com/github/app/issues/2309)：桌面端 `data.db`、共享事件路径及大文件读取问题的公开报告。桌面数据库是内部格式，读取前检查结构，不承诺未来版本不变。

以上公开资料用于确定已支持的形状；合成夹具不冒充真实客户端样本。遇到新格式应停止并补适配，不放宽检查或修改源数据。
