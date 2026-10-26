# 2026-10-23 Mac 与 Windows 功能同步

## 2026-10-26 当前进展

本轮继续完成Mac，不以源码ZIP作为最终交付。候选preview.19带当前Windows的所有共享修正，并补内核启动身份：真正launchd不同TZ反例已由失败变为通过，通知同用稳定时间。两芯片完整冻结报告正在重新生成。

Copilot的Darwin路径已不再直接unsupported，而是官方签名/任务/编辑内容保护下查找明确的原生Reload动作；没有明确动作就拒绝，避免发送猜测快捷键或重启用户Agent。新增原生合成窗口审计与23资产发布门槛。官方空白runner只能验证登录页，登录后的命令可用性、列表切走找回仍是剩余验收项；此项完成前 functionalParityComplete 仍为false。下方历史“适配缺失”描述由此更新，但不能把条件适配当成真实客户端已验收。

## 2026-10-24：当前Windows修复的Mac复查

本轮新增当前项目7条与压缩原文的MacApi/实际引擎检查，保留独占CLI的边界、原档与源只读；Mac中文/空格/大小写项目分别核对。Mac打包新增与Windows相同的7项冻结兼容审计，覆盖v4非可移植状态归档、完整工具配对、未知格式拒绝、普通Cursor搬家与两轮合成保存、压缩导出和截断保护。新版依赖、spec及这份原生打包门槛都纳入当前源码指纹。

最新统一源检查报告为 `artifacts/macos-current-fixes-checked/report.json`。既有智能原档/独立项目/重复复用/撤销、续跑停止与开机自启、重置新措辞/中文/北京时间/日历/通知独立性全部重新运行合成回归。当前Windows连接不能替代Mac本机Cocoa与launchd验收；下述Copilot自动刷新缺口仍明确未解决，整体不宣称已通过功能对等。

最终385项通过（共享规则35、后端236、续跑安全75、页面39），0失败、0跳过，源码指纹一致。最新开发快照位于macos-current-fixes-delivery，包含本轮全部源码和这份报告；未生成Mac DMG、不替换当前Windows独立预览，不发布。

## 功能复核结论：尚未达到用户要求的完整对等

用户要求的是当前 Windows 已有功能和操作体验在 Mac 同样可用。上轮“同步代码已完成”的说法过早；355 项源码检查没有覆盖 Mac 搬完后自动刷新 Copilot 的路径，不能据此宣布对等。

已用全隔离合成资料复现：完整原档及独立项目保存成功后，将平台切到 Darwin，`copilot_refresh.refresh(passive=True)` 返回 `unsupported`；继承的 `Api.open_memory_desktop` 随即返回错误，未调用打开链接。完整搬家的 Mac 提示仍要求用户自行退出/重开，自动刷新也没有与 Windows 对齐。这是实际功能缺口，不只是尚未实测。必须在 Mac 接入并验证安全刷新：有任务或未发送草稿时不打断、不强退、不丢内容；空闲后显示新列表并能切走再找回。不能凭猜测添加按键、重启或只打开链接就算解决。

本次已修正两处确定问题：PyInstaller 使用准备后的预览元数据来生成独立应用标识；重置页面区分成功更新时间和失败尝试时间，不再把旧缓存显示成刚更新。更新审计仅把专用临时副本改为正式标识并重新签名，用原有严格更新器验证；实际预览保持独立，生产更新器继续拒绝预览包。

下面“共享/已接入”仅说明代码路径，不能等同于完整功能验收。自动刷新缺口，以及原生窗口、通知、登录自启和目标客户端显示未验证之前，整体状态保持“未完成对等验收”。最新接续包和源码报告应使用本节之后的复核结果，不再使用上一份开发 ZIP。

复核修正后的固定源码检查为 `artifacts/macos-parity-recheck/report.json`：358 项通过（规则 34、后端 211、续跑安全 75、页面 38），0 失败、0 跳过，明确记录 `functionalParityComplete=false`、`nativeMacVerified=false`。接续 ZIP 位于 `artifacts/macos-parity-recheck-delivery/`，清单和报告均保留未完成项。

本轮以当前工作区全部未提交的 Windows 改动为功能基线。Git HEAD 仍为 `644fc12372b57102e40a7137b95c7c8294e05a64`；Windows 正式版 v0.3.16、Mac 公开 preview.18 都未替换。本轮没有提交、推送、标签、PR 或发布授权。

用户已确认 Windows 同一条对话重复智能搬家后，Copilot 只显示一份；这是这一项的用户反馈，不是所有功能或发布的验收。本轮用户要求全部同步到 Mac，并确认后续有 Mac 可执行原生验证。当前开发机器为 Windows。

## 功能对照

| 功能 | Mac 实现 | 当前证据 |
| --- | --- | --- |
| 完整对话搬家、只复制和源只读 | 继续使用现有共享引擎与 UI | 共享来源/导入回归；实际 Mac 客户端仍需验收 |
| ChatGPT当前桌面项目记录完整列出，独占CLI分开 | 完整桌面目录与当前项目归属优先于历史启动标记，其他CLI仍独立；共用压缩原文读取与完整/智能导出 | MacApi合成7条/压缩原档/只读与POSIX路径回归，真实Mac列表待验收 |
| 智能搬家只提供 Copilot 桌面端 | 共享目标列表与两步流程 | 页面桥及 MacApi 检查 |
| 完整原档、本地索引、中文检索和按需分页读取 | 共享 memory_store/server；同一个 APP 的 `--memory-service` 在加载 Cocoa 前提供只读 stdio | Windows 上实际启动 Mac headless 入口的 JSON-RPC 验证；冻结 Mac 握手待执行 |
| 独立资料项目、原名称加智能标识、原项目保护 | 共享 memory_workspace/deploy/desktop | 合成项目、原生登记、字节和结构保护回归 |
| 重复搬家沿用正常入口，旧失效登记不阻断 | 共享本轮最终修复和 1.1.31 精确规则 | 原档、旧行、旧资料和后续工作保留；MacApi 重复操作验证 |
| 搬完自动刷新 Copilot 左侧列表并打开；切走后仍可找回 | **Mac 自动刷新适配缺失，智能打开会返回错误** | 合成资料已复现，必须在 Mac 补齐和验收；当前不对等 |
| 用户确认的要求、完整迁移退路、安全撤销 | 共享真实 API 和 UI | 共享真实页面/Python 桥与回归 |
| 搬运中不能退出或被更新打断 | 共享任务锁，Mac 更新 gate 同步包住智能操作；关闭事件忙时立即返回，不等待写锁卡 UI | 并发和退出检查 |
| 5 小时额度等待恢复，周额度按原规则使用可用重置卡 | 共用已有自动续跑算法与提交前停止保护 | 续跑回归；不真实用卡或请求模型 |
| 续跑总开关、登录自启、退出工作台后继续 | 同 APP 原生后台及 LaunchAgent；增加已核对的身份、开始时间、OS 锁和就绪轮询 | 模拟身份/控制回归；实际 launchd、登录和退出待 Mac 检查 |
| 关闭续跑后不再续跑、不继续提交用卡 | 共用停止保护；只发送有归属的正常停止请求，取消 SIGTERM 兜底 | 停止与在途保护回归；已提交的请求不能撤回 |
| 自动续跑与重置消息同页、已有 Agent Logo | Mac HTML/CSS 复用现有外壳和品牌资源 | 宽/窄页面、侧栏、键盘与恢复检查；浏览器截图为合成数据 |
| Tibo 消息、历史补查、中文要点、北京时间、历史预告、日历 | `ResetBridge.csproj` 直接编译链接 Windows 的四份现有规则源文件，不另写一套判断 | 共用规则自检及实际 JSON 桥验证；Mac 两芯片运行待执行 |
| 关工作台窗口后仍可弹中文提醒 | 同一 APP 的独立 accessory 通知入口，拥有 OS 锁和精确身份；不显示进程管理 UI | 合成生命周期验证；原生窗口/弹框/进程验收入口已实现，待 Mac 执行 |
| 消息开关与续跑独立，看到消息不会自动用卡或暂停 | 共享通知去重与有效期；只有点击“暂停自动续跑”才关闭续跑与自启 | 独立开关、默认不调用续跑、明确按钮才暂停的检查 |
| 更新/撤销/移除不影响其他副本或任务 | 自己的提醒 token 正常交接；已核对的续跑可由用户开关控制，另一包的更新/卸载不停止它 | 身份、PID 复用、另一包保护和等待物理退出检查 |

## 共用规则与打包

Mac 的重置组件直接链接 `workspace/ResetNewsService.cs`、`ResetNewsDiscovery.cs`、`ResetNewsPresentation.cs`、`ResetCalendarModel.cs`。查询频率、官方原文核对、30 天历史、时间歧义、过期预告文案、提醒窗口和去重与 Windows 同源。第三方发现来源不等于 X 官方实时流；不能保证没有遗漏，失败时保留历史并标明未更新。这些边界也与 Windows 一致。

Mac 打包增加开发机的 .NET 8 SDK；普通用户的 APP 自带运行组件，不安装 .NET、Python、Node 或新的 CLI，不需要 API Key，不调用翻译/摘要模型。自包含运行组件会增加包体；实际大小须在 Mac 构建后报告，不用 Windows 估算值冒充。

`scripts/package_macos.py --local-preview` 使用独立 `cn.aifirst.tools.preview` 标识、本地预览标题和 memory-preview 资料/提醒目录，不下载正式更新，不自动恢复正式续跑设置，不消费正式版更新回执。续跑开关是用户明确操作时对已核对后台的控制，不能把“预览”当作不会生效。

原生包必须通过：self、memory、codex-import、reset、reset-rules、smoke、network、update、resume 报告，再生成 DMG。未来 preview.19 起的暂存/独立核验要求两架构共 21 个资产及新增必需项；codex-import必须来自Darwin冻结运行，包含7项当前保护且模型请求为0，不会用旧版或Windows报告代替。当前没有调度 GitHub Actions、创建草稿或发布。

## 本机验证与 Mac 接续

本机源码检查入口：

```sh
python scripts/check_macos_parity.py --ui
```

该入口先编译共享规则，再检查搬家、MacApi、续跑、页面及安全边界，记录源码摘要并拒绝检查途中源码变化。报告明确 `nativeMacVerified=false`。浏览器检查需要开发依赖和本机 Edge/Chromium；不表示执行过 Cocoa、launchd 或 Mac 二进制。

本轮最后固定源码报告为 `artifacts/macos-parity-final-checked/report.json`：共享规则组件构建通过；规则 33、后端 209、续跑安全 75、页面 38，共 355 项通过，0 失败、0 跳过，源码前后摘要一致。开发快照由 `scripts/package_macos_development.py` 导出，包含全部当前源码、逐文件摘要与该份报告，ZIP 和源文件重新核对后生成 SHA-256。它不是 Mac 运行包，不包含真实聊天、认证或构建缓存。

在 Mac 的独立开发目录中继续，先安装既有开发依赖（Python 3.13、Rust 1.96.0、Apple Command Line Tools）及 .NET 8 SDK。不要把它们描述成普通用户需要安装的依赖。

```sh
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r macos/requirements.txt
cargo +1.96.0 build --release --locked --manifest-path txcript/Cargo.toml
mkdir -p dialog-mover/bin
cp txcript/target/release/txcript dialog-mover/bin/txcript
python scripts/package_macos.py --architecture "$(uname -m)" --local-preview
```

只在匹配芯片的真实 Mac 构建。先完成当前芯片；另一芯片要在对应硬件/runner 验证，不能用模拟平台或交叉编译替代。打包只生成独立本地 APP/DMG，不安装覆盖 `/Applications`。不使用 Developer ID、公证、Gatekeeper 关闭或批量解锁脚本。

必须继续验收：原生 APP 初次及重复打开、Cocoa 日历和窄布局、原生提醒可见且默认不暂停、提醒弹框打开时的正常交接、关闭窗口后的提醒、退出和登录自启、智能与完整搬家在真实目标列表的显示及切走点回。测试只用合成资料；真实模型续聊和实际额度/重置卡效果由用户明确决定，不能擅自发请求。

技术依据：通知退出回调覆盖普通和模态运行模式，避免提醒对话框拦住自身正常退出；参见 [Apple 主线程指定运行模式调用](https://developer.apple.com/documentation/objectivec/nsobject-swift.class/performselector%28onmainthread%3Awith%3Awaituntildone%3Amodes%3A%29?language=objc)。这是实现依据，仍须原生运行报告验证。
