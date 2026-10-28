# 在 Mac 的 ChatGPT 中继续开发

## 当前发布：preview.22

新增更新后的简短变化弹窗，与Windows0.3.19共用whats-new.json；可点版本号回看，单版已关闭不自动重复。已公开preview.22，固定源码72e3914、构建40631620654成功；两芯片各134项原生检查与23份资产摘要通过。新增bundledReleaseHighlights、nativeReleaseHighlightsDialog、releaseHighlightsAcknowledgement三项门槛；启动和更新审计模式不自动弹框干扰其他检查，smoke用隔离资料实际手动打开并检查已读状态。旧Copilot真机边界保留。

## 上一轮发布：AI一手工具箱 preview.21

产品名已统一为“AI一手工具箱”。[preview.21](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.21) 已公开，固定源码db1842171ce10cc3ed342e579f981c08673ab940，原生构建40305808109两芯片各131项通过，23份资产摘要与报告已核对。旧.app物理名、可执行文件、bundle ID、用户资料与LaunchAgent身份保留；本地化显示名、原生进程名、窗口及DMG卷名使用新名。系统本地化、Finder显示名与进程名均实际通过，不只比对源码。原登录Copilot接续边界保持。

## 上一轮独立预览：preview.20

两架构运行包已完成并上传，固定源码44b7e21，普通40286406179及独立40286421067通过，各129项原生检查。下载开发草稿的20版Apple或Intel独立DMG，不再使用下方旧19包；报告和校验和与新包一起提供。Windows请用公开正式v0.3.17。

Mac接续只需按MACOS-NEXT-VALIDATION.md核对已登录Copilot真实菜单及侧栏；不要要求用户重复介绍需求或提供账号密码。真实模型多轮未代测，整体对等验收标志保持false。

## Windows 正式升级补充

Windows固定枚举资料绑定不改变Mac资料布局；ResetBridge宿主仍显式传入Mac既有目录。preview.20必须使用最终提交重新构建，不套用旧包报告。两芯片原生及已登录Copilot接续边界保持。

## 2026-10-26 preview.20 重置修订

当前源码候选升至preview.20，包含周末重置消息的完整修正；共享44项与源码/页面414项通过，详情见RESET-NOTICES-QA.md。本轮原生构建通过后使用新的20包，不能继续用下方fc54ad4的19包声称已含修正。已登录Copilot的实际列表仍按MACOS-NEXT-VALIDATION.md接续，不读取真实正文或认证，不发模型请求。

## 2026-10-26 当前交付与接续入口

fc54ad45e8f348f94bc717d5abf6d99e765ab8de已生成两芯片运行包。独立预览40266306041、普通候选40266303179的Apple/Intel原生任务均成功，当前源/页面405项通过；具体报告与边界见MACOS-QA.md。使用当前独立DMG，不使用旧4e4fdec源码ZIP或公开preview.18代替本轮修正。

独立APP名称“AI一手工具箱预览”，与正式应用不同名，不覆盖正式安装；内置运行组件，不要求用户另装开发工具。实际续跑开关仍按用户明确操作控制已核实的后台，不能擅自替用户开关。

用户已同意稍后在Mac继续；按[Mac接续检查](MACOS-NEXT-VALIDATION.md)直接核对已登录Copilot的真实菜单与侧栏，不再询问是否有Mac或要求账号密码。此项及真实模型多轮未验收，整体functionalParityComplete仍为false，不能拿以下源/冻结合成通过代替。

## 2026-10-26：原生完成工作正在进行

本轮用户已要求提交代码/打包并继续完成 Mac，旧段落的“禁止提交发布”不再作为本轮限制。当前候选 preview.19，继续保留 Windows 正式版和 Mac 已公开 preview.18；未通过完整报告的候选不公开。

已在真实 Apple/Intel runner 执行新功能检查，原生续跑暴露 launchd 的时区差异：ps lstart 不是稳定身份值。隔离 LaunchAgent 已复现同进程/同锁却识别失败，改为内核微秒启动时间后同一反例通过；通知后台也使用这一实现。现有包/任务不操作。

Mac Copilot 新增严格的 AX 适配：核实官方签名/单窗口、任务与全部可读编辑框，再只执行明确标注的 Reload 命令。无明确命令、权限不足、草稿或活动任务则停止；不猜刷新键、不重启软件。冻结合成窗口增加真实草稿/忙碌/原生菜单/WebKit重载检查，preview.19暂存要求23资产。官方1.1.32空白runner停在登录页，未发现可用刷新命令；已登录客户端的命令与侧栏仍须核对，不能因适配代码或合成窗口通过就宣称对等完成。

## 2026-10-24 当前修复的 Mac 专项复查

这轮接续必须包含最新 ChatGPT 压缩原文、项目7条显示/来源归属、v4导入兼容保护、重复智能搬家及当前续跑/重置代码。不能使用10月23日导出的旧源码包，也不能把旧公开Mac包当作包含这些未提交修复。

已补 `MacApi` 的实际合成入口检查：当前项目7条可搬、压缩完整原档、只终端记录不混列、中文/空格/大小写路径不合并、既有目录和源字节不变。Mac冻结入口新增 `--codex-import-test --report <文件>`，调用与Windows相同的7项完整导入/两轮保存回读/压缩导出/损坏保护检查。打包在生成DMG之前执行；未来preview.19起两芯片的暂存验证必须包含这份真正Darwin冻结报告（共21资产），不得用Windows源报告替代。

源报告使用 `artifacts/macos-current-fixes-checked/report.json`；检查覆盖实际共用代码、MacApi、续跑安全、重置规则及浏览器页面，记录源码与requirements/spec/构建门槛摘要。它不是Cocoa、launchd、真实目标软件或真实模型续聊已通过的证明。完整/智能搬家实际显示、系统提醒、登录自启仍须在Mac本机运行合成资料验收。已知Copilot自动刷新适配缺口继续未通过，不能绕过任务/草稿保护靠强退重开来“修复”。

本轮最终385项全部通过、无跳过，报告保持未完成原生验收。接续包在 `artifacts/macos-current-fixes-delivery/`，是包含全部当前未提交代码和校验报告的开发快照，不是可直接安装的Mac预览。接手后先验证包内DEVELOPMENT-SNAPSHOT.json，再在真实Mac匹配芯片构建独立local-preview；新codex-import冻结门槛、既有通知/登录自启与目标列表检查必须一并通过，仍禁止提交或发布。

2026-10-24后续：ChatGPT项目少记录/压缩本地原文修复已接入共用chatgpt/mover及新增codex_history；requirements与Mac spec增加zstandard==0.23.0，后续须带当前源码与新依赖重建。窗口/总量/损坏帧及原文编号校验保持，临时解压不写源目录。Windows合成验证见CODEX-SOURCE-QA.md；不代表Mac原生已通过，也不消除下述Copilot刷新缺口，旧ZIP不包含本轮修正。

2026-10-24：Day18分类、已完成帖后时间预告、双记录日历及过期预告不弹通知已修改直接共用的 Windows C# 源码；便携 ResetBridge35项通过。没有更改 Cocoa/launchd，也没有在 Mac 运行；既有列表自动刷新缺口和原生验收未因此完成。最新 Windows 包保留 v4 搬家修订，但用户第二轮续聊错误仍未根因确认。详见 RESET-NOTICES-QA.md、CHATGPT-IMPORT-QA.md。先前导出的 Mac ZIP 不含这次更新，不能当当前交付。


## 当前待验证：2026-10-23 Windows 全功能同步

后续共享修正：Cursor → ChatGPT 首次续聊的非可移植推理/hosted/compaction 状态已改为无损历史归档，格式 v4，见 CHATGPT-IMPORT-QA.md。本机 60 项及 Windows 冻结验证通过，Mac 使用同一源码；此项没有解决下述自动刷新缺口或替代 Mac 原生验收。上轮 Mac 接续 ZIP 早于该修正，继续时须携带当前共享源码，不能拿旧 ZIP 的 358 项报告称当前源码已测。

**最新复核：尚未完全对等，不能直接交付。** 优先处理实际缺口：`dialog-mover/core/copilot_refresh.py` 对 Darwin 直接返回 unsupported，导致智能搬家 `open_memory_desktop` 报错，完整搬家也没有 Windows 的安全自动刷新。须在 Mac 验证官方客户端的安全刷新方式，不打断任务、不丢草稿，不用仅打开链接冒充列表刷新；补齐后验证列表显示、切走找回和重复一份。上轮“代码同步完成”及 355 项成功报告不足以覆盖此路径。独立预览标识与旧缓存更新时间错误已在后续复核修正，详情见功能清单顶部。用户在意的是功能及操作体验一致，不是版本称谓。

用户要求把当前 Windows 未提交改动全部同步到 Mac。实现与对照见 [功能同步清单](MACOS-WINDOWS-PARITY.md)。包括智能搬家的完整原档/索引/只读 MCP/独立项目/重复复用/1.1.31 兼容和完整退路，以及自动续跑、中文 Tibo 提醒、北京时间和历史日历。重置规则直接共用 Windows C# 源文件；Mac 另接 Cocoa、系统后台和 LaunchAgent。

当前 Windows 已完成可运行的合成检查；Mac 的真实 APP、原生通知、launchd 和两芯片运行报告仍待执行，不得称 Mac 已实测。用户明确表示有 Mac，后续在 Mac 接续。接收独立源代码快照时，保留其中全部当前修改，不从 GitHub 拉取旧文件覆盖；不重置/clean/stash pop，不恢复旧实验，不读取真实聊天或认证，不发送模型请求。

使用 `scripts/package_macos.py --architecture "$(uname -m)" --local-preview` 生成独立预览，按同步清单准备开发依赖。该预览采用独立标识、资料和提醒状态，禁止正式更新；不替换用户正式安装。现有 Windows 预览继续保留。未经进一步明确验收授权，不提交、推送、打标签、PR、调度发布或公开 DMG。

可给 Mac 新对话：

> 请接手这个独立目录，先读 AGENTS.md、docs/DEVELOPMENT-CONTEXT.md、docs/MACOS-WINDOWS-PARITY.md、docs/MACOS-HANDOFF.md 和 docs/MACOS-QA.md。这是包含 Windows 全部未提交改动的同步快照，不能拉取旧版覆盖。先核对源码校验清单，然后在本机芯片构建独立 local-preview，执行完整原生报告并修复失败，再给我一个预览。不安装覆盖正式版，不停止现有 Agent 任务，不读真实聊天/认证，不发模型请求，不提交或发布；另一芯片未测就明确记录。

以下为先前已公开版本和开发历史，不能当作本轮新功能已验收的证据。

当前公开 [preview.18](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.18)，包和标签固定 `851887ba4903d3bb8b79e8b344950223f915737f`。Copilot v2 使用原生图片、正常角色问答和默认折叠的历史归档；旧格式可重搬一次，旧副本保留。两架构原生构建 39124685770、13 资产独立下载核验 39125691806 和匿名公开选择/摘要/十份报告通过。保留完整内置续跑；Windows v0.3.15 的更新 helper 进度与清理调整仅限 Windows。列表链接只请求导航，不能保证缓存失效，Mac 在任务完成后完全退出 Copilot 再打开。Desktop 实际显示只验收 Windows 1.1.30；未发模型请求、未升级或重开用户工具箱。详见 MACOS-QA.md 和 COPILOT-RELEASE-VERIFICATION.json。

此前公开 [preview.17](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.17)，源码 `d15b0ee80240f0de0c29730edb7574738feca680`。Copilot 搬入完成打开原生会话管理页刷新列表，已搬过副本也能查看；保留 preview.16 的完整内置续跑。两架构原生构建与 13 个资产独立下载核验通过，匿名更新从 preview.16 选到 preview.17。Copilot 实际窗口验证仅限 Windows 1.1.30，未称 Mac Desktop 已验收。由用户自行自动更新，不替其升级或重开工具箱。证据见 MACOS-QA.md、COPILOT-RELEASE-VERIFICATION.json。下文保留历史交接。

此前公开 [preview.16](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.16)，安装包源码 `f6efcc44ae34e2505c79a41754439f862587e49a`。同一个工具箱 APP 完整内置自动续跑页、Python 后台与按芯片校验的原生运行组件，不要求用户安装额外工具。两架构原生资源/页面/HTTPS/更新/续跑分别 11/10/3/9/8 项全通过，13 个资产独立下载核验通过，公开更新选择正常；源码与构建证据见 MACOS-QA.md。后台关闭防拉起、实际 launchd 自启、重复入口单实例、更新状态恢复、隔离 APP 移除后的退出与自启清理已验证。没有操作用户真实 Mac 或测试付费模型请求。下文为历史交接记录。

Copilot Desktop 搬入与列表修正已随 [preview.15](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.15) 公开，源码 dcdf5ad，两架构 131+1+10 项及 7/9/3/9 项冻结检查、全部 11 资产独立下载核验通过。当前更新入口选择较新的 preview.16，并确认保留相同 Copilot 适配；Windows 对应 v0.3.13。用户要求只提交和发布，由用户使用自动更新，不替其升级或重开本机。证据见 COPILOT.md、MACOS-QA.md。

此前公开 [preview.14](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.14)，安装包源码 `9a4626188bab5a7f63750ce7352de1a2384554a4`。自动检查无回复时增加 10/30 秒超时恢复与迟到响应隔离；旧脚本两项失败，修复后 20 项界面检查通过。两架构原生 7/9/3/9 项冻结检查、全部 11 资产独立核验通过，匿名选择确认 preview.12 能选到 preview.14。用户 Mac 实机根因和提示仍未验收；不要把“公开接口能选到”说成“其设备已经自动提示”。Windows v0.3.11 同源码修复六小时负缓存，原开发目录另一项内置续跑工作未覆盖。证据见 MACOS-QA.md、UPDATER-QA.md；下文为历史记录。

此前公开 [preview.13](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.13)，安装包源码 `249684ec97e651ec7f47267df266f20fd0434eed`，新增 Copilot Desktop 本机历史搬出。两架构各 120+10 项及 7/9/3/9 项冻结检查通过，11 个原资产独立下载核对后公开；匿名更新选择与公开校验清单核对通过。范围、共享会话标签和未验收边界见 [COPILOT.md](COPILOT.md)、[MACOS-QA.md](MACOS-QA.md)。

## 可直接给新对话的背景

> 我在继续开发 feifeigong/ai-first-tools。先读 AGENTS.md、docs/DEVELOPMENT-CONTEXT.md、docs/MACOS.md 和本文件，再检查 Git、Mac 架构与最近 CI，不重复已完成修改。AI一手工具箱面向非技术用户，当前自制工具是对话搬家。Windows WPF 保留；Mac 是 Python/pywebview Cocoa/WebKit 单窗口，共用 dialog-mover UI、Python 业务、修改后的 txcript。GitHub 发布 DMG，不上商店，不用 Developer ID/公证。根据我提供的错误排查，保持只复制、搬运中不强退、实际 Logo、真正隐藏侧栏和简单操作。不要读/上传真实认证、Cookie、聊天，先用隔离合成记录。不要把回读称为所有原生显示/续聊通过。

历史背景不是新的操作授权；当前需求、文件和最近验证结果优先。

前一版 [preview.12](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.12)，安装包源码 `553584b7bca40f13c1f0aaee2713fb82ba1d17f6`：修复八步准备完成后的状态锁、桥返回/关窗交接，保留 preview.11 全部 Cursor 历史兼容修复。两架构各 104+10 项、7/9/3/9 项冻结检查和真实窗口按钮更新均通过；独立核对 11 个资产后公开，Windows 106+30 项通过且公开 Windows 包不变。详细证据与用户设备验收边界见 MACOS-QA.md。

本轮已发布：用户更新停在“释放安装包（8/8）、15 秒”，并确认窗口/取消均卡住。已复现启动 helper 持有状态锁、页面等待桥返回时保留旧步骤；锁定框架源码还显示关窗先于桥回信的竞争。修订为后台启动和短锁状态，页面排空在途更新请求后用不需回信的异步 callback 关窗，失败只回收本次 helper。新冻结审计实际点窗口更新并要求父进程退出，不再绕过交接。用户已卡住的旧更新器仍需在无搬运任务时关闭，再手动替换 preview.12；不能将本轮归因于旧 preview.8，也不能称已在用户设备验收。

## 获取代码（仅开发者，普通用户下载 DMG）

```sh
git clone https://github.com/feifeigong/ai-first-tools.git
cd ai-first-tools
git status --short
uname -m
sw_vers
```

已有项目先查未提交修改，不重置、不覆盖。分支 `master`，提交以 GitHub 最新记录为准。

## 开发与运行

需要 Python 3.13、Rust 1.96.0、Apple Command Line Tools。下载包自带组件，这是开发要求，不是读者安装要求。

```sh
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r macos/requirements.txt
rustup toolchain install 1.96.0 --profile minimal
rustup default 1.96.0
cargo build --release --locked --manifest-path txcript/Cargo.toml
mkdir -p dialog-mover/bin
cp txcript/target/release/txcript dialog-mover/bin/txcript
python scripts/prepare_macos.py
python macos/entry.py
```

源码启动会发现真实来源，但不自动搬运。不要全量转储环境、聊天或认证。

## 自动验证与打包

```sh
cd dialog-mover
python -m unittest test_chatgpt test_close_safety test_doubao test_macos test_macos_updater test_macos_native -v
cd ..
python scripts/package_macos.py --architecture "$(uname -m)"
```

- `test_macos`：路径、中文空格/URI、只读 DB、系统打开、版本选择、UI/Logo 复用。
- `test_macos_native`：真实 Mac 引擎在隔离合成存储中对文件型目标导入/回读，核对编号、路径与源文件不变；拒绝不匹配 DB。
- OpenCode 需额外原生 CLI，这批文件型目标检查不包括它。
- 冻结包 `--self-test` 验证资源与引擎；`--smoke-test` 隔离业务目录和更新回执，在不改系统 HOME 的前提下打开真实 Cocoa 窗口，验证 WebKit/Python 桥、侧栏和 API，避免测试环境破坏 WebKit。
- preview.3 的 `--update-test` 在临时 APP 副本中检查实际 helper、原子交换、备份和 Cocoa 重启；不要在作者安装目录运行测试替换。下载、取消、忙碌等待、失败恢复的单测在 test_macos_updater；流程与限制见 MACOS-UPDATES.md。
- preview.2 新增冻结包 `--network-test`：在不存在的 Python CA 路径环境中，用系统 Keychain 验证 HTTPS、读取本项目公开 GitHub 发布列表；失败阻止 DMG 发布，不记录代理地址/认证/环境。
- CI 仅给打包步骤提供一次性只读 `AI_FIRST_CI_UPDATE_TOKEN`，只由 `--network-test` 显式传入请求，报告仅记录是否使用授权。普通更新不会读取此变量或 GH_TOKEN，安装包不包含授权，用户无需配置令牌。这样避免公共 runner IP 的匿名查询限流，不绕过 TLS 或把网络失败当通过。
- `test_doubao` 覆盖 Mac Default、Windows/旧布局、自定义工作区、仅云端缓存、空账户和导出路径一致性。原生测试新增合成本机豆包轨迹 → Claude Code → 回读，保持源文件不变；会话列表快照为合成替身，不表示真实豆包版本已人工验收。
- JSON 在 `artifacts/macos/<架构>/` 和 Actions 产物；不是所有原生目标软件的人工测试，没有发下一轮模型消息。

## 真机验收清单

1. Finder 下载、DMG 挂载、拖入应用程序、未签名首次打开的实际提示。
2. 一个窗口和 Dock 应用，Logo/中文、全屏、系统红黄绿按钮正常。
3. 侧栏真正隐藏、图标切换、鼠标无蓝框、键盘焦点可见。
4. 来源标题/目录/时间/任务/归档过滤/数量/正文与原软件一致。
5. 低风险记录搬运，核对标题/正文/模式/文件夹，原记录不变。
6. 到目标原生软件查找打开，再由用户决定是否发下一条，避免自动收费请求。
7. 分别验收 ChatGPT 本机 Work/Codex、Claude Cowork/Claude Code，云端保持不可写。
8. 重复搬运、目标占用、空正文、格式变化、权限不足、断网、搬运中退出、恢复。
9. 更高版本且含当前架构才提醒；下载替换不删设置/Agent 数据。

每项记提交、系统/芯片、来源/目标版本、步骤、预期/实际、是否写入/备份，不把未执行用例标通过。

## 问题定位

| 现象 | 检查入口 |
| --- | --- |
| 黑屏/打不开/模块缺失 | CI、spec、Cocoa/PyObjC、资源路径、最低系统 |
| 软件没出现 | common.py、sources.py、真实数据位置、是否已有记录 |
| Mac 豆包工作没出现 | core/doubao.py；Mac 是 DoubaoWork/Default，不是 Windows User Data/Default；刷新会重新寻找软件 |
| 检查更新失败 | macos/updates.py、truststore._macos/_scproxy；按 errorCode 区分证书、DNS、超时、限流；不要关闭 TLS 校验 |
| 目录乱码/斜线/重复项目 | URI、POSIX、chatgpt._norm，不强行 Windows 大小写折叠 |
| 搬完不显示 | 模式、DB 结构、项目/索引、原生客户端版本，不只看文件存在 |
| ChatGPT 格式变化 | codex_import.validate，先查结构，不放宽安全检查 |
| 续聊失败 | Mac shlex.join、原生 CLI、目标模式 |
| 查看位置无反应 | common.open_external 参数与权限 |
| 许可证/打包失败 | TOC、Python/PyObjC 元数据、Cargo metadata、资源 |

工具箱状态：`~/Library/Application Support/AI一手工具工作台/`；搬家缓存/历史/备份：`~/Library/Application Support/对话搬家/`。不要上传整目录。自定义 CODEX_HOME 可由启动环境提供；Finder 不保证继承终端环境，后续可加明确设置，不全盘扫描。

## 发布维护

- 上轮公开 preview.6，构建源码 9703d4335043526fe3ad0ecb00fdba6e31b83ac4，两轮两架构各 74 项单测和资源/窗口/HTTPS/更新四类冻结检查通过，11 个资产独立核对后发布。自动查询失败提示并按 1/5/15/60 分钟退避，限流等一小时；Cocoa 的两套 UI 等原生 loaded 后 ai-first-ready 信号才初始化。49 项本地定向及完整 21 项浏览器回归通过。源码标签取真实构建提交，文档未重做包。preview.1/2 必须最后一次手动替换，preview.3/4 可软件内更新；用户真实公网升级与第三方续聊仍未验收。
- preview.5 源码 6fe261b86e9764e855f71fa32236d567c2970591 首轮通过但重复 Intel 的首个窗口检查失败，故保持未公开，不移动标签。不要把安排了启动查询说成用户机器已成功检查，也不能直接断言网络原因。先复现静默错误/提前调用，再验证新的恢复与就绪信号，过程见 MACOS-QA.md；不要重复应用已完成修订或用初次绿色掩盖重复失败。
- preview.4 构建源码 7dcc96f9f77c9b1a2bd714560521ef0b1dc64756。同源码两次完整构建的两架构各 73 项单测和资源/窗口/HTTPS/更新四类冻结检查通过；独立核对 11 个上传资产后发布。源码标签对应实际构建，后续交接文档未重做包，旧版本的公开资产保持不变。
- preview.3 的追加隔离重启曾出现 WebKit 页面未加载。996cfb4 保持系统 HOME 的审计修订未完全解决；7dcc96f 避免启动时异步清理共享 WebKit 存储，同时保留随机 localhost 端口，两次两架构复测通过后发布 preview.4。不要重复应用修补、放宽窗口审计或把旧版首次成功说成重复稳定。机制和自己的页面缓存变化见 MACOS-UPDATES.md、PRIVACY.md。
- 已发布 preview.2 的构建源码 `8674f6f`，修复豆包工作识别/刷新及系统 HTTPS；历史链接、校验见 MACOS-QA.md。
- 首批两架构包构建源码为 `2b49c7f`，Mac/Windows CI 均通过；构建链接、SHA-256 和未验收项见 MACOS-QA.md。后续只整理交接文档，不能把文档提交说成重做了安装包。
- 两架构 DMG 名称 `AI-First-Tools-<release>-macos-<architecture>.dmg`，附 SHA-256。
- CI/报告通过才发布下载包；源码提交不等于已发布应用。
- 发布前准备与 macos/version.json 同版本的草稿；两架构 build 任务通过后，先在已验证构建提交准备同名 lightweight Git 标签，不移动既有标签。stage-release 校验标签提交、DMG 哈希、四类报告、版本/架构，只暂存 11 个原资产，草稿仍不公开。若仅末尾暂存失败，使用 Stage verified release assets，输入 macos 和原构建 run_id；不要重新编造报告或把新源码包混入旧版本。独立下载核对报告、资产 digest 后才公开。
- scripts/stage_macos_release.py 只处理已有匹配草稿；草稿不存在或已发布就跳过，禁止自动覆盖公开版本。失败的构建不会进入上传步骤。
- 暂存成功状态可能只是跳过；必须核对草稿 tag_name、11 个实际资产和日志中的 Validated assets staged。发布脚本不再修改 target_commitish；真实来源取 Git 标签，避免工作流文件标签权限导致暂存失败。
- 更新拒绝草稿/旧版本/错误域名/不匹配架构。
- 不加 xattr 解锁脚本，不关闭 Gatekeeper，不宣称苹果审核。
- Windows 与 Mac 的下载和更新能力分开说明。

进展以 MACOS-QA.md 和当前 Actions 为准。Windows 仅验证共享业务/浏览器布局，真实 Mac 应用由 macOS runner 检查；最终第三方列表/续聊由作者实机验收。
## preview.8 自动提醒（历史发布）

用户的 Mac 具体安装版本尚未取得。代码层已复现六小时检查间隔/没有返回补查、初始化首次失败不恢复的缺口；preview.8 修复提醒调度，并保留已验证更新包的临时网络失败状态。每十分钟后台补查、返回/恢复连接至少两分钟间隔、失败退避不被事件打断；关闭提示条保留按钮。原生冻结 Cocoa 新增「自动出现按钮」和「不擅自下载」检查；旧版须先取得本版才能运行新调度。

已公开 preview.8，源码标签 `5e669f20af6b19c808889e4d4c320fbd4740200d`。主分支构建 `38560496836` 与标签完整复测 `38560504847 / attempt 2` 两架构各 83+3 项及四类冻结检查通过；发布资产全部取前者，11 个文件独立下载核对，公开 feed 从 preview.2/3/4/6/7 选到 8、同版不提示。标签首轮 ARM 重启后页面加载超时，失败包未发布，证据和校验值在 MACOS-QA.md。不把这些检查当成用户 Mac 的实际手点验收，不承诺所有 WebKit 启动问题都已修好。

Windows Chat 搬出失败只记录在 KNOWN-ISSUES.md，按用户要求后修。

## 本轮补充：preview.7 长对话分页导入

- 当前已公开 preview.7，源码标签 `12aa483b9191ee4772cbfaa288dd9429a23f047f`。发布资产取主分支 `38527937388 / attempt 2`，两架构各 80+3 项检查和四类冻结报告通过；11 个上传资产独立核对，公开更新器两架构从 preview.2/3/4/6 选到 7，同版本不提示。
- 同源码标签构建 `38527943205` 两架构也通过。首轮主分支 Intel 更新后窗口加载超时，失败产物未发布；保留证据，不声称消除了所有 Cocoa 偶发加载问题。具体包 SHA/大小与全部边界见 `MACOS-QA.md`。

- 用户现象是 Cursor → 本机 Work 只显示尾部，上翻「重试」无效；不是更新检查问题。
- 旧版原生 `thread/read` 通过不等于分页通过。旧 legacy 导入可复现 `thread/items/list` 返回不支持；见 `dialog-mover/test_codex_native.py` 新增长对话测试。
- 新导入用 paginated 元数据、完整 `item_completed`、稳定轮次/消息 UUID、从零连续 ordinal；保留原协议内容，不手写目标分页数据库，让目标原生恢复线程建立投影。
- 旧版搬过的记录更新后重新搬一次，创建新副本，不修改旧副本或源。新格式成功后恢复去重。
- 新增 `test_codex_history.py` 完整性/格式/旧去重回归；Mac CI 下载 SHA 固定的官方 0.162.1 引擎，三个原生历史测试均禁止模型请求。CI 测试引擎不进入发行包。
- 不把原生引擎分页验证说成用户 Mac 的 ChatGPT 界面手工滚动或实际发送续聊已经完成。发布状态以 GitHub 和下一节 QA 为准。

## 历史发布：2026-10-15 preview.9 迁入历史续聊长度修复

- 用户已确认错误出现在发送下一条消息后。preview.7/8 验证分页和回读，没有覆盖真实续聊请求中历史工具字段的长度；不能据此说续聊已通过。
- `codex_import.py` 在生成分页历史前，为超长/非法工具名称和调用编号建立稳定的兼容映射，调用与结果成对，重复编号分配唯一别名；合法名称预先保留，避免别名碰撞。原字段保留在记录的 `dialog_mover_original`，正文、思考、参数与结果不截断；配对缺失/类型不符停止导入，不放宽格式检查。
- 导入格式升为 `paginated-import-v2`，旧成功记录允许创建一次新副本，之后恢复去重；不自动修改源或用户已经继续聊过的旧副本。
- 新增 `test_codex_replay.py`：隔离合成 Cursor 数据库 → 实际搬家 → 原生引擎 `exec resume` → 仅监听 127.0.0.1 的模拟 Responses 服务。关闭兼容映射时，85 字符调用编号/工具名分别复现同样的 400 长度拒绝；开启后普通、超长、重复编号和自定义补丁的五类测试通过，补丁不重新执行，参数/结果完整，源不变。全程不使用真实认证、不请求在线模型。
- 本机 92 项共享/格式/原生分页、26 项界面及 5 项续聊检查通过。Mac 两架构各 87 项共享、8 项原生分页/续聊及四类冻结检查通过；发布包取 `38691055276 / attempt 2`，源码标签固定 `12391ab6431a9f2cbc77b5650aec51ad9bc925c2`。独立发布核验 `38693214923` 下载并逐个比对原 CI 与草稿的全部 11 个文件、大小和 SHA-256，通过后公开 preview.9（发布 ID `413485163`）。首轮 ARM 更新后页面未加载的失败报告保留，未发布失败产物；细节及真机验收边界见 MACOS-QA.md。
- Windows 普通 Chat 搬出问题仍仅记录，不重发 Windows 安装包；本轮未更改更新请求频率或 GitHub 限流机制。

## 2026-10-15：校验更新包长时间等待与取消不响应（preview.10 已发布）

用户确认下载后“校验更新包”超过三分钟且点击取消仍不变。当前接入 Windows，未取得用户 Mac 的具体阻塞步骤；不能把代码缺口说成已确定该设备的系统原因。已用隔离应用复现：旧 prepare 在首个应用校验后收到取消，仍复制文件并生成任务，不抛 Cancelled。

新增准备阶段共用 180 秒预算、每个外部操作至多原有 60 秒，命令等待每 0.2 秒检查取消/预算并结束自己的子进程；文件遍历和分块哈希也检查。完整性摘要算法保持一致，版本/架构/链接/资源封印/原子替换检查未放宽。失败清理先判断实际挂载状态（包括 attach 已挂载但命令未成功的情形），十秒限时卸载；仍挂载时保留目录。已停止准备后的私有暂存目录后台清理，避免清理阻塞取消界面。不强退工具箱或其他 Agent，不触碰源对话。

界面显示八个实际步骤和已用秒数，取消请求明确显示“正在取消”，确认工作线程停止后才显示取消结果。三分钟是准备预算，不包括下载或故障后卸载/清理，也不承诺系统单次文件调用异常阻塞时严格按秒返回。

新增真实子进程取消/共享预算、取消后不复制不建任务、摘要兼容、挂载失败不递归清理、取消状态和慢清理不阻塞界面的隔离回归。冻结更新审计改为从隔离真实 DMG 走 prepare 的挂载/复制/核验/卸载八步，再验证实际 helper 替换与 Cocoa 重开；下载传输使用合成资产的本地替身，HTTPS 独立审计仍保留，不称为用户公网完整升级。上述准备修复已随 preview.10 发布，原生与发布资产核验结果见本节末尾。

已安装旧程序的更新器不会随源码修改改变。若当前取消也不响应，等待没有搬家任务后正常退出并重开；核对实际版本，必要时手动换到通过验证的新版。不能指示用户强退搬运任务、关闭系统保护或直接删数据库。

### 同轮追加：更新后原生窗口导航顺序

候选源码 59510c1 的构建 38695442363 两次完整执行中，八步准备均通过，但首轮 Intel、第二轮 ARM 分别在更新后重开出现同一 WebKit 页面未加载失败；未创建公开 preview.10，也未创建它的标签。两份 update-test 报告保留，不用继续重跑凑通过。

检查锁定的 pywebview 6.2.1 Cocoa 源码发现，WKWebView 在 didFinishNavigation 后才被放入 NSWindow。新增同步 before_show 挂载网页视图，使首次 loadRequest 执行前已进入窗口；这是针对复现启动停滞的修订假设，不把代码阅读当作用户设备根因的确定证据。仍等真实 loaded 才注入应用就绪信号，不清理共享 WebKit 数据、不固定端口、不关闭 TLS、不延长窗口测试等待。

冻结 smoke 新增 nativeContentAttached 门槛，更新审计在完成一次真实更新重开后，再从同一目标执行一次独立原生重开，二者均通过才报告成功。新增隔离单元用例确认挂载不伪造 loaded 或执行 JS，并拒绝“桥就绪但原生内容未挂载”的报告。此处为候选阶段记录；最终构建和发布核验见下文。

参考：[Apple WKWebView](https://developer.apple.com/documentation/webkit/wkwebview)；具体框架顺序以锁定版本的 Cocoa 源码和本轮原生报告为准。


### preview.10 发布完成

[公开下载](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.10)。安装包与不可变标签源码为 `c4b97abe25478ea777386d860af9ae9633823f65`，后续文档提交不重做二进制。[原生构建](https://github.com/feifeigong/ai-first-tools/actions/runs/38729691064) 的 arm64、x86_64 各 96 项共享/隔离检查、8 项原生分页/本机模拟续聊检查通过；冻结资源 7 项、Cocoa 页面/桥/自动提醒 9 项、系统 HTTPS 3 项、更新 6 项均通过。更新审计从隔离真实 DMG 走八步准备，再执行 helper 原子替换、备份保留、实际原生重开与再次独立打开；下载传输仍为合成资产本地替身，未冒称用户公网全流程。页面通过 Cocoa 直接读取包内 ui，文件读取范围和窗口导航均受限，原生 Python 桥正常。

[独立发布核验](https://github.com/feifeigong/ai-first-tools/actions/runs/38730802705) 单独下载原 CI 资产与草稿的全部 11 个文件，名称、大小、SHA-256 及标签源码完全一致后公开（发布 ID `413752467`）。匿名生产更新选择实测两个架构从 preview.1–9 选到 preview.10，同版不提示；公开 SHA 清单与核验报告相符。[Windows 源码回归](https://github.com/feifeigong/ai-first-tools/actions/runs/38729691054) 的 98 项后端、27 项界面、WPF 构建及自检通过，Windows 安装包保持 v0.3.8。

已卡住的旧更新器需在无搬家任务时正常退出，手动安装本版一次；旧更新器不会随发布自行改变。原 64/85 字符错误的旧目标历史仍需从 Cursor 重搬为新副本，源与旧副本保留。未操控用户真实 Mac、未请求在线模型，不保证系统单次磁盘调用异常阻塞时严格按秒返回，也不将当前两架构通过称为所有 Mac 和原生客户端永久无故障。早期候选失败与取消的报告/运行继续保留，未发布失败包。
