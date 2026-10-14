# Mac 移植验证记录

## 2026-10-14 preview.5 自动检查恢复（验证中，尚未发布）

用户确认当前安装 preview.2：手动检查能看到新版，启动却没有提醒。复查实际标签源码发现，自动查询失败只在手动模式显示错误，preview.2 又只尝试一次；preview.3/4 同样隐藏自动错误，仅在六小时后再查。存在这些代码缺陷并不证明已确定用户 Mac 当次失败是 DNS、超时或代理问题，没有读取其电脑日志。

- 用合成 API 重现结构化网络失败、桥异常静默以及短时间不再检查：修复前两种失败的通知断言失败，自动重试断言超时；不是将未检查到误报为最新。
- 修复后首次失败显示非阻塞的「将自动重试」；普通错误按 1/5/15/60 分钟退避，持续错误最多每小时一次；GitHub 限流直接等一小时。成功后恢复六小时检查，手动成功取消旧重试；用户关闭错误提示后继续后台检查但不反复弹提示。下载/更新中延后版本查询，不重入安装。
- 定向浏览器 7 项及追加 2 项均通过，包含两种自动错误、限流、退避/关闭提示、手动查询替换待重试任务、下载中延期，以及既有单次点击/等待搬运/取消/布局。这里只测共享页面合成 API，没有运行作者 Mac 或访问 Agent 数据。
- 版本提高为 preview.5，不覆盖已公开 preview.4。两架构原生构建、上传资产核对和公开更新选择尚待本次运行完成；当前公开包仍为 preview.4。

## 2026-10-13 preview.4 一键更新与重启修复（当前已发布）

[公开下载](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.4)。构建源码 `7dcc96f9f77c9b1a2bd714560521ef0b1dc64756`，Git 标签指向同一提交；文档提交不重做二进制。

- [发布资产所属运行](https://github.com/feifeigong/ai-first-tools/actions/runs/38357964353) 与 [同源码重复运行](https://github.com/feifeigong/ai-first-tools/actions/runs/38357970395) 均成功，两次的 arm64、x86_64 各 73 项共享/隔离原生单测通过。四组真实 macOS 15 冻结 APP 都通过 7 项资源/引擎、5 项 Cocoa/WebKit/桥、3 项真实 HTTPS、4 项更新检查以及 ad-hoc 封印和 DMG 格式校验。
- 本次发布使用 38357964353 的两个架构，不混用重复构建的二进制。该运行的 stage-release 日志确认实际上传，而非跳过；发布前独立下载原产物，核对标签、四类报告和 11 个上传资产的大小及 SHA-256 digest，全部匹配后公开。
- 两架构实际执行冻结 helper、交换前自检、系统原子交换、保留旧 APP 备份、新版 Cocoa/WebKit/Python 桥重启及版本确认；报告 helperReturnCode=0、receipt/preflightReport=true、五项 relaunchChecks=true。使用临时 APP 副本和合成旧版本元数据，不是从已公开旧二进制在作者安装目录手点升级，也未实际执行 Mac 原生整包公网下载/挂载的完整更新回路。
- 针对 preview.3 后续重启失败，保持系统 HOME 的审计修订仅使 ARM 复测通过，Intel 仍失败。检查锁定 pywebview 6.2.1 Cocoa 实现后推测共享数据异步清理与页面加载竞争；本版避开该清理路径，保留随机本机端口、系统 HOME 和严格 HTTPS，增加两项回归，重复原生构建通过。未取得全部系统错误诊断，不把推测当成已证明所有平台行为。
- 发布后用匿名公开 GitHub 列表运行生产选择/完整性逻辑：两架构 preview.3 和 preview.2 都选择 preview.4，preview.4 不提示同版本；实际下载公开校验文件并核对 DMG 的 digest/大小要求及哈希条目。此检查在 Windows 宿主运行纯 Python 逻辑，不冒称 Mac 冻结 APP 的用户公网完整升级已经验收。
- [本源码 Windows 回归](https://github.com/feifeigong/ai-first-tools/actions/runs/38357964354) 通过 75 项后台、15 项浏览器与工作台自检，WPF 构建零错误/警告；未重新发布 Windows 包。Windows 安装/下载证据见 UPDATER-QA.md。
- 未更新作者真实 Mac 安装，未读取 Agent 对话/认证，未发送模型请求。preview.1/2 最后一次手动替换到本版，preview.3 可软件内升级。Finder/Gatekeeper、macOS 13/14、真实用户完整公网升级及第三方原生显示/续聊仍待验收。

| preview.4 文件后缀 | 大小（字节） | SHA-256 |
| --- | ---: | --- |
| `macos-arm64.dmg` | 23016126 | `b4f68a65bd1da45ee5885ba23f2c8cce1be12844cac6e641e20295296a38ccd2` |
| `macos-x86_64.dmg` | 23924220 | `567ff29c16615785ab3cc6a278dbd4f79133fa9fed1fb5db974e15bbb4bd33eb` |

以下是历史版本的证据，不代替本版验证；已经公开的同版本文件保持不变。

## 2026-10-13 preview.3 一键更新（历史已发布）

[公开下载](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.3)。构建源码 `957c22611b127514b58b839a1662e458bb7fc956`，Git 标签指向此提交；后续发布流程与文档提交未重做这些包。

- 软件内下载/进度/取消、搬运中自动等待和完成后重启。Windows v0.3.8 沿用原有更新事务；Windows 忙碌时提示结束任务后重试，不将其说成自动等待。见 UPDATER-QA.md。
- [两架构原生构建](https://github.com/feifeigong/ai-first-tools/actions/runs/38352056433) 的 arm64、x86_64 build 任务均成功：macOS 15 各 71 项共享/隔离单测，以及冻结 APP 的 7 项资源/引擎、5 项 Cocoa/WebKit/桥、3 项真实 HTTPS、4 项更新检查全通过；ad-hoc 资源严格校验和 DMG 格式校验通过。
- 更新检查在临时 APP 副本中构造旧版本元数据，实际执行独立 helper、系统原子交换、旧版备份保留、新版 Cocoa/WebKit/Python 桥重启及版本确认。这不是从已公开 preview.2 二进制在作者电脑手点升级，也不是实际联网下载整个更新包的原生全流程。单测另覆盖下载、取消、损坏、架构/版本、指纹变化、忙碌保护和失败恢复。
- 早期原生更新检查发现重启后的 WebKit 页面不加载；先修复独立冻结进程重启及 helper 的审计状态隔离，所选构建两架构检查通过。测试状态与记录路径仍在受控临时目录，失败包未发布。当时本地 Mac 共用/更新单测 36 项、浏览器 4 项通过。
- 原构建末尾 stage-release 因更改工作流标签权限失败，不能将整条运行说成成功。改为先准备指向已验证源码的不可变标签，再仅上传报告通过的原资产。[最终暂存运行](https://github.com/feifeigong/ai-first-tools/actions/runs/38353974861) 成功；前一次暂存因草稿标签不匹配跳过，没有上传资产，不能用绿色状态冒称完成发布。
- 发布前独立下载原构建产物，对四类报告及 11 个上传资产逐一核对版本、架构、大小和 GitHub SHA-256 digest。随后公开同一草稿，不替换已公开同版本文件。
- 发布后用匿名公开列表调用生产版本选择和完整性资产检查：两架构 preview.2 都能选到 preview.3，preview.3 不提示同版本；实际下载公开校验文件并核对 DMG 条目。此项在 Windows 测试宿主运行纯 Python 选择/下载逻辑，不冒称 Mac 冻结应用已实际联网下载整个 DMG 并更新。
- 未更新作者真实 Mac 安装，未读取 Agent 对话/认证，未发送模型请求。preview.1/2 仍需最后一次手动替换；首次打开/Gatekeeper、macOS 13/14、实际用户网络及第三方客户端显示/续聊尚待真机验收。

| preview.3 文件后缀 | 大小（字节） | SHA-256 |
| --- | ---: | --- |
| `macos-arm64.dmg` | 23340151 | `ffb8adb3c2078e9be0a3d5456d580d4fcf493951ca58f0e3938e6be37e1e7a45` |
| `macos-x86_64.dmg` | 23923783 | `312127bd9a0a6d44fdcdc9540647f3d21c59ab2d9ea2fbd7ba7138033e59255a` |

以下 preview.2、preview.1 是历史记录，不是 preview.3 的验收证据。

### 发布后追加复测

同一运行代码随后在 [追加运行一](https://github.com/feifeigong/ai-first-tools/actions/runs/38353318206) 的 ARM 及 [追加运行二](https://github.com/feifeigong/ai-first-tools/actions/runs/38353312883) 的两架构隔离更新检查中仍出现 Cocoa pageLoaded=false，localhost 页面可读取但原生桥未开始注入。未用这些失败包替换公开资产，不将初次通过说成所有重复运行都稳定。

排查发现 --smoke-test 仍在创建 Cocoa 前改写 HOME；996cfb4 改为仅隔离业务 home() 与更新回执，保持系统 HOME，继续排除真实来源/数据。此提交只调整显式审计模式，正常用户的 home() 与启动环境不变；本地新增隔离安全回归后 37 项通过。[该修订原生运行](https://github.com/feifeigong/ai-first-tools/actions/runs/38355445903) 的 ARM 通过，Intel 重启页面仍未加载，因此不能视为完整解决。后续 7dcc96f 调整 WebKit 启动，本地 38 项定向测试及两次两架构 CI 通过后，另发 preview.4，证据在本文件顶部。公开 preview.3 仍对应原构建 957c226，没有用新测试包冒充原资产。

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
- preview.1/2 没有自动替换；preview.3 加入此能力，preview.4 修复追加重启问题并重复通过隔离原生审计，用户真实安装的手点公网完整升级仍待验收。

测试全用临时目录/合成记录，不导入真实账户、不发模型请求；按 MACOS-HANDOFF.md 继续真机验收。
