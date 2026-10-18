# Copilot Desktop 对话搬家

2026-10-18 已发布修订（[Windows v0.3.14](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.3.14) / [Mac preview.17](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.17)，构建、原生检查及全部资产独立下载核验通过）：修复搬入后 Desktop 仍显示旧列表的问题。在 Windows 已安装的 Copilot Desktop 1.1.30 中复现：索引与正文已存在，窗口关闭再开仍复用后台进程；进入原生 Manage sessions 后查询到新记录，Chats 侧栏随之更新，点击能打开正文。此前官方 CLI 严格恢复检查没有覆盖这个界面刷新环节，不能替代 Desktop 验收。

新流程在每批完成后调用官方本机 `ghapp://chats`，再进入 `ghapp://recent`，使已经停留在会话管理页的重复搬运也重新进入查询页面；不退出或终止 Copilot，不发送消息。结果提供「在 Copilot 中查看」和失败重试。已搬过记录沿用去重，仍提供同一个列表入口，因此 v0.3.13 的旧副本无需再复制。此入口打开会话列表，不声称按编号直接打开聊天：`ghapp://sessions/<编号>` 在该 Desktop 版本会明确拒绝普通 Chats。官方入口参见 [GitHub 深链接文档](https://docs.github.com/en/copilot/how-tos/github-copilot-app/open-with-deep-links)。Windows 实机已验证新版打开流程和原记录正文；Mac 共用该流程，Mac Desktop 实机尚未验证。

Windows 搬入与列表修正版已公开 [v0.3.13](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.3.13)，构建与独立下载核验通过。Mac 搬入与列表修正版已公开 [preview.15](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.15)，两架构构建与全部资产独立下载核验通过；下文早期版本保留为历史。

已随 [Windows v0.3.10](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.3.10)、[Mac preview.13](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.13) 公开。已有支持一键更新的版本可检查更新；更早版本下载完整安装包。构建与独立资产核验见 [Windows QA](UPDATER-QA.md)、[Mac QA](MACOS-QA.md)。

当前支持 GitHub Copilot 独立桌面 App 的本机历史搬出和搬入：在「对话搬家」中选择 GitHub Copilot，按标题或文件夹搜索、勾选记录、选择现有目标和文件夹。支持刷新重新发现记录。搬入后登记到 Desktop 的 Chats（聊天）列表。VS Code 自身的 chatSessions 不在本轮范围。

## 来源和识别

Windows 和 Mac 都读取用户目录下 `.copilot/session-state/<会话编号>/events.jsonl`。只读取这一层已知会话路径，不扫描电脑，不读取 Cookie、登录配置、凭据、工作文件或附件，也不启动 Copilot、SDK 服务或模型。

Desktop 与 CLI 共用上述存储，不能把所有 `session-state` 文件夹都当成桌面聊天。列表只枚举 `data.db/sessions` 已登记且未归档、未删除、非临时占位的桌面会话；命令行独有记录、未登记目录不再混入。只查询白名单会话字段以及工作区/项目的名称与位置，不读取认证、账户或配置内容。初始化过 Desktop 才显示入口，只有 CLI 不算安装 Desktop。

普通聊天统一归入「聊天」，不把 `.copilot/chats/…/file-c-users-…` 内部沙箱目录当作项目。项目会话用 `workspaces/projects` 的登记名称和路径分组。只有索引、没有本机正文的正式会话仍显示为不可搬运；临时占位和孤立空目录不会凑数。搬运前重新检查归档、删除及索引成员关系，未知结构或占用直接报错，不回退到混列共享目录。

2026-10-16 用户截图中的「Image-text alignment fix」与 Desktop 登记对应；原界面的 19 条包含共享存储中其他客户端的会话和无正文孤立目录，不能代表 Desktop 的 19 条聊天。截图中的内部路径编码不是项目名。当前修订把列表来源收紧为 Desktop 登记；运行中的新会话数量仍可随用户使用改变，不固定为某个数字。

## 搬入 Copilot Desktop

在来源（包括 ChatGPT 普通聊天、本机 Work/Codex）选择已有完整正文的记录，目标选 GitHub Copilot，选择工作文件夹后确认。每条创建一个新的 UUID 聊天副本并登记为 `general_chat`，位于 Desktop 的 Chats，而非自动新建项目或 worktree。v0.3.14 / preview.17 起会打开会话管理页以刷新侧栏，点击搬入标题查看；若系统未能打开本机链接，结果显示重试入口，并提示从 Copilot 用户菜单进入 Manage sessions。

这是对本机格式的适配，不是 GitHub 官方提供的跨软件历史导入 API。先检查会话表字段和必填项；格式变化、数据库占用、未知正文块时停止。消息转换为版本 1 的连续事件：原用户/助手角色与完整文字、时间保留；思考通过 `assistant.message.reasoningText` 保留，因为原生恢复会过滤独立 `assistant.reasoning` 事件。工具调用/结果、系统说明和附件信息转为明确标注的历史参考文字，不作为可执行工具或新系统指令。附件文件和原项目环境不迁移。

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

只搬对话历史，不复制文件、附件、登录状态、工具权限或原工作环境。目标原生客户端是否显示、是否能继续发送下一轮，需要分别验收，不能以生成文件或回读通过代替。

读取器逐字保留消息正文。目标适配仍遵循原有格式，例如 WorkBuddy 的用户消息回读会去掉正文首尾空白；不承诺所有目标的排版字节完全一致。

## 开发验证

`python -m unittest test_copilot -v` 使用隔离目录和合成事件。覆盖 Windows/Mac 路径、桌面/共享来源区分、长正文、工具配对、中断调用、子任务交错、损坏与变化、未知结构、归档删除、仅云端索引、刷新和可搬入目标。引擎存在时额外实际搬入 Cursor、Codex、本机 Work、Claude Code、WorkBuddy 国内/海外版并回读，验证源文件字节不变及重复搬运。

`test_import_ui` 新增 Copilot 搜索、选择、刷新、桌面标记、损坏记录禁选、ChatGPT → Copilot 文件夹选择/确认/结果检查；`test_agent_icons` 校验随包原版图标和来源摘要。Windows 检查、Windows 打包和两种 Mac 架构的 CI 已纳入上述测试。CI 结果和安装包状态以实际运行报告为准；未对用户的真实 Copilot 数据或付费模型续聊作自动验收。

`test_copilot_import` 覆盖 125 轮完整正文、Desktop 登记、工具历史说明、ChatGPT 导出接线及去重、未知结构/触发器、失败回滚和已有目录保护。`test_copilot_native` 在独立空账户目录启动校验值固定的官方 Copilot 1.0.98 测试组件，完整分页读取全部事件，禁止修复地恢复会话，再逐字段比较所有原始事件，包括思考和长工具说明。请求白名单不含发送消息、登录、工具执行；测试组件不打包给用户。Windows、两种 Mac 架构均执行该原生检查。当前依据 Desktop 1.1.29 的索引形状，其他版本需通过同样的结构检查。

原生历史读取和严格恢复不等于已在用户 Desktop 上逐条人工滚动或发送付费下一轮。没有对用户安装做合成导入或升级操作。实际构建与发布验收见两份 QA。

图标提取自已安装 GitHub Copilot App 的程序资源，未重画、未改色，随软件打包，运行时不联网获取。资源来源与 SHA-256 见 `dialog-mover/ui/assets/agents/sources.json`。

## 依据

- [GitHub：Copilot 会话数据](https://docs.github.com/en/copilot/concepts/security-governance-and-network-settings/session-data)：CLI 和独立 App 的共享本机记录、会话索引和云端范围。
- [GitHub Copilot SDK 事件定义](https://github.com/github/copilot-sdk/blob/main/python/copilot/generated/session_events.py)：事件与字段的公开定义；本适配不依赖或运行 SDK。
- [GitHub App #2309](https://github.com/github/app/issues/2309)：桌面端 `data.db`、共享事件路径及大文件读取问题的公开报告。桌面数据库是内部格式，读取前检查结构，不承诺未来版本不变。

以上公开资料用于确定已支持的形状；合成夹具不冒充真实客户端样本。遇到新格式应停止并补适配，不放宽检查或修改源数据。
