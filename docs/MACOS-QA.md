# Mac 移植验证记录

## 2026-10-13 preview.2 修复与验证

- 用户确认打开的是豆包工作 / Agent 模式。首版发现逻辑仅拼接 Windows `User Data/Default`，Mac `DoubaoWork/Default` 被遗漏；现统一列表、本机任务判断和导出使用的工作区，保留旧布局及显式 DOUBAO_WORK_DIR。刷新重新发现来源，不将普通豆包聊天伪装成可搬运 Agent。
- 首版打包没有冻结应用 HTTPS 测试，且使用默认 Python CA 路径和统一连接失败提示，不能从该提示判断用户具体的证书/网络问题。现使用 Mac 系统信任库、系统代理与分类提示，禁止关闭证书/主机名校验和跨地址重定向；失败提供官方项目下载页，不报告已经最新。
- 本地 Windows：共享业务/导入回归 71 项通过；新增刷新发现来源用例后的浏览器/Logo/启动回归 18 项通过；最终代码定向 Mac 共用单测 23 项通过。3 项原生 Mac 用例在 Windows 明确跳过，不用模拟平台声称运行过 Mac 二进制。
- 首次 CI 发现新网络失败用例依赖本机已准备的打包版本资源：本地有旧资源而全新 runner 没有。改为合成版本 fixture 隔离测试，不放宽应用网络检查；完整重跑成功，失败/被替代的运行包不发布。
- 随后 `b98b478` 构建的 ARM 网络检查因 GitHub 公共 runner IP 匿名限流失败，错误分类明确为 rate_limit；没有放宽网络检查，也不发布该包。早先 `26a2983` 两架构匿名 HTTPS 检查已通过，记录在 [先前运行](https://github.com/feifeigong/ai-first-tools/actions/runs/38342256226)，但这些包被后续构建替代，不是本次下载资产。
- [最终 Mac 两架构成功运行](https://github.com/feifeigong/ai-first-tools/actions/runs/38344666096)，构建源码 `8674f6f24d6e027134ec63c285815ce808f7ec4f`。arm64、x86_64 各 58 项共享/隔离测试通过，包括合成豆包本机轨迹 → Claude Code → 回读、源文件不变。列表快照使用合成替身，不等于真实豆包 IndexedDB 人工验收。
- 两架构冻结 APP：7 项资源/引擎检查、5 项真实 Cocoa/WebKit/桥检查、3 项网络检查全部通过；在不存在的 SSL_CERT_FILE/SSL_CERT_DIR 环境中真实读取本项目 GitHub 发布列表，证书及主机名验证保持启用，`_scproxy` 可加载。最终 CI 网络探测使用当次一次性只读授权规避共享 IP 限流，授权不写入包，普通更新不读环境令牌；报告只记录 authenticatedProbe。CI 没有模拟用户的实际代理配置，不保证其网络一定连通。
- 两架构 ad-hoc 资源严格校验、DMG 格式、下载后的 SHA-256 核对通过。CI 只把报告通过的同一运行资产暂存到匹配版本草稿，独立下载后再核对 9 个上传资产的大小和 digest；最终公开前仍需人工确认，不覆盖已发布版本。[Windows CI](https://github.com/feifeigong/ai-first-tools/actions/runs/38344666214) 通过 60 项后台、13 项浏览器及工作台自检/构建（零警告/错误）；本次没有重发 Windows 安装包。
- 没有访问作者 Mac，也没有读取真实豆包数据库、验证其当前版本的原生列表或发送模型消息。作者的网络/原生软件显示情况仍需新版真机验证；Mac 13/14 也未验收。

| preview.2 文件后缀 | 大小（字节） | SHA-256 |
| --- | ---: | --- |
| `macos-arm64.dmg` | 22432380 | `9ad6c2d134d8114d2ddcb4083585dc0ae50f0ca76ec2e1933a8abccd0d93d835` |
| `macos-x86_64.dmg` | 23903075 | `b1e88e2bff705a82b98eb29c91ba0c5a5e78e398b5a4f5a9852483609525dedb` |

以下是已发布 preview.1 的历史记录，不应当作 preview.2 已通过的证据。

版本 0.4.0-macos-preview.1；2026-10-12 两种架构原生构建、隔离检查和 DMG 校验通过。仍是预览版，不表示所有第三方软件已经真机验收。

构建源码：`2b49c7f49a6acab31abcbd1518415ba8b9188230`。发布前的后续提交仅整理文档，未改动运行代码或包内资源。

[通过的 Mac 构建与报告](https://github.com/feifeigong/ai-first-tools/actions/runs/38246950148) · [通过的 Windows 回归检查](https://github.com/feifeigong/ai-first-tools/actions/runs/38246950152)

## Windows 已通过

- 共享列表、关闭、隐藏启动、Logo、UI 回归：40 项。
- 新 Mac 路径、URI、只读 DB、系统打开、版本选择、资源复用、空测试账户和 Cocoa 加载握手：14 项。
- 新工作台浏览器布局/完全隐藏侧栏/更新提示：1 项，960–1440 宽度。
- 既有导入测试：19 项通过，另 2 项 Mac 原生测试在 Windows 明确跳过。
- Windows 工作台自检：62 项通过，构建零错误/零警告。
- 不表示在 Windows 运行过 Mac 二进制。

## Mac 已通过

| 检查层次 | Apple Silicon / arm64 | Intel / x86_64 |
| --- | --- | --- |
| macOS 15 本机编译修改后的 txcript | 通过 | 通过 |
| 共享安全、Mac 路径、隔离目标导入测试 | 40 项通过 | 40 项通过 |
| 冻结 APP 的 7 项资源/引擎检查 | 全部通过 | 全部通过 |
| 真实 Cocoa 窗口、WebKit/Python 桥、侧栏状态/完全隐藏、空账户 | 5 项全部通过 | 5 项全部通过 |
| 加入许可证后的 ad-hoc 资源封印严格验证 | 通过 | 通过 |
| DMG 格式校验和下载后 SHA-256 核对 | 通过 | 通过 |

40 项测试中包含 12 个文件型目标的合成记录导入/回读，以及不兼容 ChatGPT 数据库拒绝写入；不是 40 种客户端人工测试，也不是全部来源×目标组合。

隔离目标：Cursor 桌面、WorkBuddy、WorkBuddy AI、千问办公、Claude Code、本机 Cowork、Antigravity 桌面/CLI、Cursor CLI、Grok、ChatGPT 本机 Codex/Work。测试核对新编号、写入位置、原始输入不变；没有启动这些第三方客户端或发送模型消息。

Actions 的 `macos-arm64`、`macos-x86_64` 产物各包含 DMG、`self-test.json`、`smoke-test.json`、校验文件。首次失败包未发布，中间被新版替代的构建也不作为下载包。

### 发布文件核对

| 文件后缀 | 大小（字节） | SHA-256 |
| --- | ---: | --- |
| `macos-arm64.dmg` | 22365154 | `21f1dc9ee8a55cff1b130c82c199a57aac8ca638bc79a10a9d45a1f1e03c4f76` |
| `macos-x86_64.dmg` | 23859487 | `bb77c443250171277fcd2dd936b4fc5571d0279e00c6769026f3f770737d2428` |

## 首轮构建发现与修复

- 首轮 ARM 引擎、隔离目标导入和冻结包自检通过；真实 Cocoa 窗口、Python 桥、侧栏检查通过，但空账户断言失败，因此没有发布 DMG。
- 原因是测试准备了空的 `COWORK_SESSIONS_DIR` 目录，按已有规则被识别为已初始化来源。改为只设置隔离路径、不创建目标目录，保留原识别规则，并增加空账户回归测试；不是放宽断言。
- 首轮 Intel 出现启动阶段 `WebViewException`；直接调用页面检查使用框架的 20 秒就绪等待。增加显式等待页面加载及超时回归测试，保留失败退出，并记录窗口/页面状态；修复后的同架构完整重跑已通过。
- 许可证收集发生在冻结应用生成之后，须重新封装 ad-hoc 资源校验并严格验证，避免资源封印与新增许可证不一致。这不是 Developer ID 签名或苹果公证。
- 临时路径核对解析真实路径，兼容 Mac 的 `/var` 与 `/private/var` 符号链接，不放宽测试目录边界。

## 尚未验收

- Finder 下载、Gatekeeper 首次打开、安装/Dock 实际展示。
- macOS 13/14；实际 runner 为 macOS 15。
- 各第三方客户端实际显示、刷新、附件/工具行为、下一轮对话。
- OpenCode CLI 不在本批文件型目标矩阵。
- Mac 自动覆盖更新未实现，只有提醒与下载。

测试全用临时目录/合成记录，不导入真实账户、不发模型请求；按 MACOS-HANDOFF.md 继续真机验收。
