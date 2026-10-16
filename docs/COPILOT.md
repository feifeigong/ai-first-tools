# Copilot Desktop 历史搬出

已随 [Windows v0.3.10](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.3.10)、[Mac preview.13](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.13) 公开。已有支持一键更新的版本可检查更新；更早版本下载完整安装包。构建与独立资产核验见 [Windows QA](UPDATER-QA.md)、[Mac QA](MACOS-QA.md)。

本轮先支持 GitHub Copilot 独立桌面 App 的本机历史：在「对话搬家」中选择 GitHub Copilot，按标题或文件夹搜索、勾选记录、选择现有目标和文件夹。支持刷新重新发现记录。暂不提供搬入 Copilot；VS Code 自身的 chatSessions 不在本轮范围。

## 来源和识别

Windows 和 Mac 都读取用户目录下 `.copilot/session-state/<会话编号>/events.jsonl`。只读取这一层已知会话路径，不扫描电脑，不读取 Cookie、登录配置、凭据、工作文件或附件，也不启动 Copilot、SDK 服务或模型。

Desktop 与 CLI 共用上述存储，目录本身不能证明是 Desktop 创建的。存在 `.copilot/data.db` 时，只以只读连接读取 `sessions` 表中白名单内的标题、目录、时间、编号和归档/删除标记；不读取 `app_state` 等其他内容。有该桌面索引成员关系的记录标为 `Copilot Desktop`，意思是桌面端记录过它，不保证最初由桌面端创建。其他本机记录明确显示「Copilot 共享会话（Desktop / CLI 共用，来源未确认）」，同一编号只出现一次。

已知归档/删除标记会过滤，搬运前重新检查。桌面索引存在但结构不识别或被占用时会停止列表读取，不把全部记录降级成共享会话。只有索引、没有本机正文的记录显示为不可搬运；不会请求云端补齐。没有桌面索引时只能显示共享存储，不能据此确认原客户端的侧栏或归档状态。

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

`python -m unittest test_copilot -v` 使用隔离目录和合成事件。覆盖 Windows/Mac 路径、桌面/共享来源区分、长正文、工具配对、中断调用、子任务交错、损坏与变化、未知结构、归档删除、仅云端索引、刷新和只读目标。引擎存在时额外实际搬入 Cursor、Codex、本机 Work、Claude Code、WorkBuddy 国内/海外版并回读，验证源文件字节不变及重复搬运。

`test_import_ui` 新增 Copilot 搜索、选择、刷新、共享标记、损坏记录禁选和只读目的地检查；`test_agent_icons` 校验随包原版图标和来源摘要。Windows 检查、Windows 打包和两种 Mac 架构的 CI 已纳入上述测试。CI 结果和安装包状态以实际运行报告为准；未对用户的真实 Copilot 数据或付费模型续聊作自动验收。

图标提取自已安装 GitHub Copilot App 的程序资源，未重画、未改色，随软件打包，运行时不联网获取。资源来源与 SHA-256 见 `dialog-mover/ui/assets/agents/sources.json`。

## 依据

- [GitHub：Copilot 会话数据](https://docs.github.com/en/copilot/concepts/security-governance-and-network-settings/session-data)：CLI 和独立 App 的共享本机记录、会话索引和云端范围。
- [GitHub Copilot SDK 事件定义](https://github.com/github/copilot-sdk/blob/main/python/copilot/generated/session_events.py)：事件与字段的公开定义；本适配不依赖或运行 SDK。
- [GitHub App #2309](https://github.com/github/app/issues/2309)：桌面端 `data.db`、共享事件路径及大文件读取问题的公开报告。桌面数据库是内部格式，读取前检查结构，不承诺未来版本不变。

以上公开资料用于确定已支持的形状；合成夹具不冒充真实客户端样本。遇到新格式应停止并补适配，不放宽检查或修改源数据。
