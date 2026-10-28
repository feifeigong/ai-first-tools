# Mac 移植验证记录

## preview.23 重置上下文候选

共用48项规则覆盖完成句式、关联证据、旧缓存重核和未知语言不自动确认；两端共用日历模型及中文词。当前候选须重新执行原生资源、Cocoa日历、通知、更新、续跑及两架构DMG验证，不能套用preview.22的134项报告。原已登录Copilot与真实模型续聊边界保持。

## preview.22 更新摘要已发布

本版新增同版一次的本次更新弹窗、版本号回看和本机已读记录。源码与浏览器检查、两芯片实际Cocoa/WebKit检查分别记录，未通过新三项门槛及既有全部检查的包不得发布。完整构建40631620654固定72e3914484d32354fc6919340ee093e0f36cc455，两芯片各134项全部通过，发布23份资产的版本/摘要/报告一致。原生已读检查要求实际文件里有本版本，不以错误后的静默抑制冒充成功。不把本轮弹窗验收扩展成已登录Copilot或模型续聊通过。

Apple更新测试首次在创建合成DMG时遇到hdiutil Resource busy；相同源码仅重跑失败任务后，更新、续跑及完整镜像验证全部通过。失败报告保留，不降低门槛或以旧版本报告代替。

## preview.21 改名验收范围

已公开[preview.21](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.21)，源码db1842171ce10cc3ed342e579f981c08673ab940，完整构建及暂存[40305808109](https://github.com/feifeigong/ai-first-tools/actions/runs/40305808109)成功。Apple与Intel各10份原生报告、131项全部通过；23份远端资产、版本、芯片、DMG校验和与GitHub摘要逐项一致。真实登录Copilot及模型续聊仍按原约定接续，未用合成结果代替。

新增localizedProductName、finderDisplayName、nativeProcessName三项原生检查；发布门槛明确要求三者。包装前写入en/zh-Hans/zh-Hant及Base的InfoPlist.strings，保留与文件名匹配的基础名称后重新ad-hoc签名。旧bundle路径、identifier、资料与LaunchAgent不改，原有更新/续跑/提醒生命周期全部仍须通过。首轮已实际通过三项名称检查；另发现更新预检运行于candidate.app，Finder按物理临时名显示属系统正常规则。现严格区分产品与本应用更新暂存范围，发布只接受finderScope=product，暂存检查不能冒充正式名称验收。

## 2026-10-26 preview.20：两架构原生报告通过

源码44b7e21fcc8a4644ad6dcd3df564af6b28badccc；普通构建40286406179、独立预览40286421067成功。Apple/Intel分别10份原生报告、129项：17资源身份、15检索/原档、7导入兼容、8提醒生命周期、44共享规则、6刷新保护、12Cocoa页面、3网络、9更新、8续跑。首次任务因Rust下载DNS或镜像资源忙失败，仅重跑失败任务，最终完整报告通过才上传，失败报告不作为交付证据。Windows当前源码/页面414项保持通过。

独立DMG及验证ZIP/SHA256SUMS已上传开发草稿并核对GitHub资产摘要、字节数；旧19包和Windows37d7525预览退出当前交付。Windows正式已另发v0.3.17。Mac实际登录Copilot菜单及侧栏、模型多轮仍待用户Mac接续；不能把本次129项合成原生检查写成真实客户端已全部验收。

## 2026-10-26 preview.20：周末重置修正接入

共用Windows四份业务源修复历史坏行整页丢失、Day20/21措辞、官方引用/回复链、5分钟失败重试和最新页独立补查。近期补充来源只有经官方核实并满足已有通知窗口才提醒；旧档案不弹，恢复网络不丢已核实近期帖。Mac日历与Windows同步显示蓝色未定时预告，不要求用户确认。源码/页面414、共享44项已通过；preview.20的两架构原生包另行构建，其结果不能引用下方preview.19的报告。实际登录Copilot侧栏及在线续聊仍待原先约定的Mac接续。

## 2026-10-26 当前两芯片运行包

安装包提交：`fc54ad45e8f348f94bc717d5abf6d99e765ab8de`。独立预览构建[40266306041](https://github.com/feifeigong/ai-first-tools/actions/runs/40266306041)、普通候选[40266303179](https://github.com/feifeigong/ai-first-tools/actions/runs/40266303179)的Apple/Intel任务全部成功。独立预览未执行正式暂存；普通任务没有匹配preview.19草稿，未改公开资产。Windows当前源检查[40266303160](https://github.com/feifeigong/ai-first-tools/actions/runs/40266303160)亦成功，已有独立Windows包继续固定37d7525，不用它冒充新Mac包的构建来源。

独立包每芯片10份原生报告：资源/独立身份17、完整原档及检索15、导入兼容7、提醒生命周期8、共用规则35、原生刷新保护6、Cocoa页面/桥12、网络3、更新交接9、续跑生命周期8。安装前后合成资料、系统launchd、外部独立Cocoa/WebKit进程、正常窗口关闭及实际DMG验证均运行；不发送模型请求，不读取真实聊天或认证。当前Windows源与页面检查405项（35+252+79+39）、0失败/跳过，源指纹一致。

冻结续跑故障有两段证据：旧ps时间在跨TZ source LaunchAgent中不稳定；改用内核时间后，302cfc7冻结报告显示PID、内核时间、OS锁、目录均匹配，仅ps程序路径不匹配。fc54ad4用proc_pidpath固定实际程序映像，命令与包身份检查仍独立保留；原先失败的launchAgentReady及其后停止、防拉起、移除清理均实际通过。未放宽格式、身份或任务保护，也不靠增加超时通过。

运行包仍不是全部真实客户端体验已验收。官方Copilot1.1.32空白runner停在登录页，只能确认未找到安全刷新命令；冻结合成6项证明保护及明确菜单重载机制，不证明已登录侧栏。用户已同意稍后在Mac继续核对命令可用性、显示/切走找回/重复一份。真实模型多轮、额度节省与长期消息覆盖保持未验收。接续见MACOS-NEXT-VALIDATION.md。

开发草稿只上传通过23项资产验证器的独立DMG；20份原生报告与源/Windows报告合为Validation-Reports-fc54ad4.zip，另附统一SHA256SUMS。旧Mac源码ZIP退出当前交付，正式Windows v0.3.16与公开Mac preview.18保持。以下为历史检查过程，以本节与GitHub实际结果为准。

## 2026-10-26：继续原生验收，preview.19候选

4e4fdec 的两芯片共享/原生读取检查通过，但冻结续跑检查在 launchAgentReady 失败，未产出可发布DMG。诊断确认实际后台正在运行且归属/命令正确，控制端报 identity_unverified。隔离真实 LaunchAgent 的不同时区反例（40260449677）复现同 PID/锁但启动时间不同；换用 proc_pidinfo 后同一检查（40260766927）六项为true。保留所有失败报告，不调整就绪超时或降低归属门槛。通知也改用内核启动时间，防止工具箱与提醒跨时区误判。

新增 copilot-refresh-test 为真实冻结 Cocoa/WebKit/AX 的独立合成窗口检查：草稿、空编辑框、忙碌、明确菜单操作、实际文档重载、原应用进程保留。这里只替换合成应用身份，不接触真实Copilot/聊天/认证；正式产品仍要求GitHub签名。preview.19资产门槛增为两芯片23项，缺该报告或旧报告不放行。

官方Copilot1.1.32公开签名包在独立runner完成原生菜单/正常关窗重开/常见按键探查，未证明登录页可刷新；正常关窗保持同进程和同文档，故不能以重开窗口冒充刷新。CLI只提供open，不提供reload。新增适配仅接受运行时真实可见的Reload命令，未知则保留任务和草稿。已登录Copilot的刷新及侧栏持久显示仍待Mac环境验证，不能将其写为通过。

## 2026-10-24 当前修复专项检查（本机为Windows）

最终固定源码报告 `artifacts/macos-current-fixes-checked/report.json`：**385项通过、0失败、0跳过**，含共享重置规则35、共享/Mac后端236、续跑安全75、页面39，源码检查前后摘要一致。已查看上轮7条项目合成页面，本轮实际页面桥与Mac日历/窄布局交互也通过。报告明确host=Windows、nativeMacVerified=false、functionalParityComplete=false，保留Copilot自动刷新缺口；本轮没有Mac运行包或真实模型续聊结论。

新增MacApi与实际本地导出引擎的合成检查，复现并确认当前桌面项目7条完整显示、5条压缩/2条普通记录可读、终端独占记录保留、项目中文空格与大小写边界正确，以及原文/原项目保持。共用v4冻结审计通过Mac入口生成带版本、架构、host/frozen边界的报告；新增CLI分派与缺报告拒绝、依赖与指纹覆盖检查。

Mac打包必须执行 `--codex-import-test`；未来preview.19起缺7项中任何一项、Windows报告、非冻结报告、存在模型请求或声称真实模型续聊通过的报告均不能暂存。这是新增检查门槛，不是本轮已经生成了Mac安装包。Apple/Intel两芯片仍须分别构建，当前没有调度CI、提交或发布。

本轮统一验证在 `artifacts/macos-current-fixes-checked/`，检查前后源码摘要须一致；先前Windows预览保持运行，不替换用户安装、不启停续跑、不读真实正文或认证。仍明确记录 `functionalParityComplete=false` 和 `nativeMacVerified=false`：Copilot自动刷新是已知缺失，真实Cocoa/通知/launchd/目标列表与在线续聊尚未执行，不能拿合成回读代替。

2026-10-24后续：共用ChatGPT项目目录和压缩原文读取/完整导出已更新，Mac冻结加入固定zstandard依赖。Windows隔离专项和页面检查见CODEX-SOURCE-QA.md；Mac须重建后验本地压缩项目的列表、完整/智能搬家及临时目录清理，不以Windows成功替代两芯片原生检查。下述整体对等未通过及安全刷新缺口不变。

2026-10-24：Day18分类、已完成帖后时间预告、双记录日历及过期预告不弹通知已修改直接共用的 Windows C# 源码；便携 ResetBridge35项通过。没有更改 Cocoa/launchd，也没有在 Mac 运行；既有列表自动刷新缺口和原生验收未因此完成。最新 Windows 包保留 v4 搬家修订，但用户第二轮续聊错误仍未根因确认。详见 RESET-NOTICES-QA.md、CHATGPT-IMPORT-QA.md。先前导出的 Mac ZIP 不含这次更新，不能当当前交付。


## 2026-10-23：功能对等复核发现遗漏，整体尚未通过

上轮 355 项成功是源码合成检查，不是 Mac 功能对等验收。此次隔离合成复现：保存完整原档/独立项目后，Darwin 的刷新结果是 unsupported，智能自动打开返回错误、未打开目标；完整搬家在 Mac 也仍是手动重开提示。这个路径此前没被报告覆盖，实际缺口不能归为单纯的“原生待测”。功能清单和 Mac 接续说明已把安全自动刷新、列表切走找回、重复一份列为优先未完成项。

已修正独立预览标识读取错误和失败检查误标消息更新时间，增加相应合成校验；正式更新校验规则不放宽，更新审计仅调整临时副本。新的源码复测在 `artifacts/macos-parity-recheck/`，检查通过仍必须记录 `functionalParityComplete=false` 和明确缺口。当前原生 Mac 仍未运行，不能声明完全满足用户要求。

本轮修正后固定源码复测：组件构建通过，共享规则 34、后端 211、续跑安全 75、页面 38，共 **358 项通过、0 失败、0 跳过**，检查前后指纹一致。该报告保留 `functionalParityComplete=false` 和自动刷新缺口；不把源码通过冒称功能对等。独立接续开发包位于 `artifacts/macos-parity-recheck-delivery/`，内含当前全部修改、此份报告及逐文件摘要；上一份交付 ZIP 不包含本轮复核修正。

## 2026-10-23：Windows 功能同步，源码完成、原生验证待执行

本轮直接在现有未提交改动上同步；Windows 同条重复搬家只显示一份已获用户确认，未获得提交/发布授权。当前连接 Windows，用户确认后续有 Mac 接续。公开 preview.18 未更换，不把下方历史报告用于本轮。

共用完整搬家/来源分类、memory 系列后端和 UI；Mac 新增同 APP 的 headless 只读 MCP，智能写入与更新/关闭相互保护。重置组件直接编译 Windows 当前四份 C# 规则，并复用其发现/核对测试；Mac 原生提醒和前端日历通过 JSON 桥使用这些结果。自动续跑增加 Mac 精确身份与 OS 锁、启动就绪、提交前停止保护和正常退出，不再以 SIGTERM 兜底。另一包的更新/卸载保留已核对的现有后台。

本机验证含共享规则、MacApi、实际 headless JSON-RPC、原档与去重、停止/身份/另一包/物理退出、两开关独立、明确按钮才暂停、日历时区和过期文案、键盘与宽窄恢复。界面图均为合成数据，不是真实 Mac 截图。最后固定源码执行 `python scripts/check_macos_parity.py --ui --report artifacts/macos-parity-final-checked/report.json`：共享组件构建通过，规则 **33**、后端 **209**、续跑安全 **75**、页面 **38**，共 **355** 项通过、0 失败、0 跳过；检查前后源码指纹一致。报告明确 `host=Windows`、`syntheticOnly=true`、`modelRequests=0`、`nativeMacVerified=false`；原生 Mac 状态仍为未运行。

新增冻结报告门槛：`--memory-test` 保存完整原档、只读服务、重复与撤销；`--reset-test` 实际独立 Cocoa 通知进程、启动者退出后保留、原生窗口关闭、中文模态提醒、模态中正常交接、另一包保护；`reset-rules-test` 在本机架构运行共用规则；smoke 新增日历及独立提醒开关。所有原生检查只使用带标记的临时资料。两个架构都须有通过报告；未来 preview.19 暂存检查拒绝缺失项，当前没有运行发布流程。

首轮统一检查被扩展 smoke 用例的旧 mock 回复数量/状态不完整拦截，报告保留在 `artifacts/macos-parity-source/`、`artifacts/macos-parity-final/`。更新合成替身以明确提供新增日历与开关状态，保持原生内容挂载失败必须失败；没有放宽实际门槛。之后检查期间又有源码修改，统一入口现对检查前后指纹进行核对；只接受最后固定源码的成功报告，不累计旧轮次数。

功能对照、Mac 构建和真实验收边界详见 [MACOS-WINDOWS-PARITY.md](MACOS-WINDOWS-PARITY.md)。独立源码包由 `scripts/package_macos_development.py` 导出至 `artifacts/macos-parity-delivery/`，包含当前全部修改与逐文件校验清单、最终合成报告和合成页面图，不包含认证、真实聊天、数据库、构建缓存或本机日志。导出脚本逐文件回读核对并生成 ZIP 的 SHA-256；不交付伪造 DMG，不覆盖安装、不提交或发布。

## 2026-10-18：preview.18 已发布，Copilot 原生图片与历史过程

[公开版本](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.18)，不可变标签与两架构包固定源码 `851887ba4903d3bb8b79e8b344950223f915737f`，发布 ID `416425797`。v2 转换用户内嵌图片为原生附件、合并正常文字并保留原角色；工具与系统记录归入默认折叠且已完成的历史归档，完整源另存回读。旧格式允许重搬一次，源与旧副本不改动。Mac 保留完整内置续跑与现有自动更新；Windows 同轮 v0.3.15 的更新阶段窗口和重开前清理调整不冒称 Mac 功能。

[原生构建 39124685770](https://github.com/feifeigong/ai-first-tools/actions/runs/39124685770) 的 Apple 芯片与 Intel 均通过共享检查、Copilot 原生完整历史/图片严格恢复、原生分页及仅本机模拟续聊、后台算法和实际冻结 APP/DMG。每架构资源/页面/HTTPS/更新/续跑的 **11/10/3/9/8** 项均为 true，包含真实 Cocoa 点击、八步准备、桥排空、父进程退出、helper 替换、备份与两次 Cocoa 重开。下载传输是隔离合成资产，系统 HTTPS 单独检查；不把它称为用户公网完整升级。

[独立核验 39125691806](https://github.com/feifeigong/ai-first-tools/actions/runs/39125691806) 分别下载原 CI 与草稿的全部 13 个文件，核对原生报告、名称、字节、SHA-256 和源码标签后公开。匿名公开元数据、SHA 清单及十份原生报告再次下载核对通过；两个架构的生产选择器从 preview.17 选到 preview.18、资产被校验器接受，同版不提示。完整资产与检查项见 COPILOT-RELEASE-VERIFICATION.json 的 nativePresentation20261018。

首轮源码 5525967 的 ARM 冻结更新审计在 fixture 阶段报 CalledProcessError，失败包未发布，具体命令当时未记录，不能归因为某个系统错误。851887b 仅补充合成夹具命令、退出码及脱敏错误诊断，并新增失败回归；没有延长超时或放宽检查。新的两架构完整执行通过，未复现该错误，原失败和被替代的 Intel 运行保留，不宣称已确定其根因。

Copilot Desktop 的图片、两轮问答、角色与默认折叠只在 Windows 1.1.30 用独立合成副本实际验收，未称 Mac Desktop 已验收，也未请求在线模型。列表导航不能保证原生缓存失效；Mac 有任务时先完成任务，再完全退出 Copilot 并打开。用户工具箱由其自行自动更新，代理没有升级或重开安装。

| 芯片 | DMG 大小（字节） | SHA-256 |
| --- | ---: | --- |
| Apple / arm64 | 149753022 | `bcd68c5f67eff1f66bf5fe078b913a4bebc28f0198a9db05840a1eb9da1f3cea` |
| Intel / x86_64 | 163165849 | `fc42efc7e9f9d7e0fa4ecbeac90a5144ad471b5ccb384a244f70498a41db93f6` |

## 2026-10-18：preview.17 已发布，Copilot 搬入后打开会话管理页

[公开版本](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.17)，两架构包和不可变标签固定源码 `d15b0ee80240f0de0c29730edb7574738feca680`，发布 ID `416401378`。每批搬入后使用官方 Chats → Recent 本机链接刷新列表，结果增加 Copilot 查看与重试，已搬过记录不重复写入。保留 preview.16 完整内置续跑与自动更新。

[两架构原生构建](https://github.com/feifeigong/ai-first-tools/actions/runs/39121374816) 的 Apple 芯片与 Intel 均完成 143 项共享检查、1 项 Copilot 原生完整历史/严格恢复、54 项后台算法及 10 项原生历史/本机模拟续聊，实际 Cocoa APP/DMG、资源、桥接、HTTPS、更新与内置后台报告全部通过。[独立核验](https://github.com/feifeigong/ai-first-tools/actions/runs/39122126090) 将原 CI 与草稿全部 13 个文件逐个下载核对名称、字节、SHA-256、报告和源码标签后公开。匿名公开元数据摘要与公开 SHA256SUMS 再核对通过，两架构从 preview.16 选到 preview.17，包被生产更新校验器接受，同版不提示。

Copilot Desktop 的侧栏刷新与已导入记录正文打开实机验证仅限 Windows Desktop 1.1.30；Mac 共用相同导航流程，没有操作用户真实 Mac Copilot 或测试付费模型下一轮。未替用户安装、更新或重开工具箱，不把生产更新选择通过称为用户窗口已经弹出提示。

| 芯片 | DMG 大小（字节） | SHA-256 |
| --- | ---: | --- |
| Apple / arm64 | 149864399 | `a50e20a4c40731a1206124bc3a1533655a8b6e19a096d3848edf4f4e699fb3b0` |
| Intel / x86_64 | 159409057 | `90437855fc6d7619317d362a7a3876c97c1ec798ca35042a075f2f62e9a2c66e` |

## 2026-10-16：preview.16 已发布，单个 APP 内置自动续跑

[公开下载](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.16)。不可变源码标签与两种芯片的安装包均固定 `f6efcc44ae34e2505c79a41754439f862587e49a`，发布 ID `415011225`。同一个 Cocoa 工具箱新增自动续跑页、包内 Python 后台入口与按芯片校验的 Codex 原生组件；不要求读者另外安装后台、Python、Node 或 Codex CLI。保留自动更新及本轮 Copilot Desktop 搬入与列表修正。

- [两架构原生构建](https://github.com/feifeigong/ai-first-tools/actions/runs/38908465473)：Apple 芯片和 Intel 均完成共享回归、原生历史/本机模拟续聊、54 项续跑算法回归及冻结 APP/DMG 构建。每架构的 self/smoke/network/update/resume 报告分别有 **11/10/3/9/8** 个检查，全部为 true。
- 新增 Cocoa 检查通过真实 JS/Python 桥切换到续跑页、开启后台开关、保存登录开关、关闭并确认两个开关回落，再返回搬家页；这部分使用隔离替身，不启动用户后台。另有独立真实冻结进程检查：无外部运行环境下原生组件和隔离未登录 app-server 握手、手动与直接重复入口只保留一个后台、登录开关不改变当前进程、关闭后直接再执行自启入口仍退出、重新开启正常、更新状态交接恢复后台和自启、实际 launchd 加载/停止及应用移除后清理均通过。
- 后台原生检查使用禁用任务的合成配置与临时 HOME/CODEX_HOME；原生 Codex 使用文件凭据模式且未登录，不接触真实账号，不请求模型。移除检查通过重命名隔离 APP 触发实际后台监测退出与登录文件清理；没有操作用户 Finder、真实注销/登录或用户正在安装的 APP。完整更新交接的九项既有检查仍通过，下载为本机合成替身，不称为用户公网升级实机验收。
- [独立下载核验](https://github.com/feifeigong/ai-first-tools/actions/runs/38910299970)：原 CI 与草稿全部 **13** 个资产分别下载，逐个核对报告、名称、大小、SHA-256 与源码标签后公开。本机又下载十份公开小报告并核对摘要，全部检查通过；匿名公开入口及公开校验文件摘要一致，两个架构从 preview.14 均能选到 preview.16，同版不提示。
- [Windows 回归](https://github.com/feifeigong/ai-first-tools/actions/runs/38908465504) 同源码通过。没有重发 Windows 安装包或替换用户安装。早期合并工作流因编码错误保留了冲突标记，语法检查失败后立即修复；后续路径规范化和完整进程命令修订均纳入最终源码。此前候选/取消构建没有发布，最终只采用本次两架构同批原资产。

| 芯片 | DMG 大小（字节） | SHA-256 |
| --- | ---: | --- |
| Apple / arm64 | 149834502 | `9a809823df779778f21052bcde7ce1c58794906c4d8d6e964cc4ed5b49f55627` |
| Intel / x86_64 | 163003083 | `b7ad50738d150e0298b3d5b1c12ad3d655806274745f099fb9c218f1bfe793a8` |

## 2026-10-16：preview.15 已发布，Copilot Desktop 搬入与列表修正

[公开版本](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.15)，2026-10-16 13:46:39 UTC 发布，标签和运行包源码 `dcdf5adad1f309d538ef795c51525c041476ce43`。修正共享存储/空目录混列、内部聊天目录误作项目，新增 ChatGPT 等来源搬入 Desktop Chats。正文/思考完整回读后登记，只新建副本，不迁移认证或权限，范围见 COPILOT.md。

[两架构原生构建](https://github.com/feifeigong/ai-first-tools/actions/runs/38908258217) 的 arm64、x86_64 各通过 131 项共享/来源/目标检查、1 项官方 Copilot 1.0.98 完整分页读取与严格恢复、10 项既有原生历史/本机模拟续聊检查；冻结资源 7、Cocoa 窗口/桥 9、系统 HTTPS 3、完整更新 9 项全通过。Copilot 测试使用隔离空账户和 125 轮合成正文，不登录、不发下一轮，逐字段核对恢复后的全部事件，包括 reasoningText。

首轮主分支 `38905927761` 因所有目标测试未初始化新增 Copilot 测试库而失败；补齐夹具后的 `38906556595` ARM 通过，Intel 被同时开发的主分支推送取消，未发布失败包。最终用隔离发布分支，额外核对本仓库精确源码已合入 master、两种原生任务和全部关键检查成功。随后原样执行既有 stage_macos_release.py / verify_macos_release.py，分别下载原 CI 与草稿所有 11 资产，名称、字节、SHA-256、不可变标签和原生报告一致后公开（发布 ID `415010334`）。[机器可读核验记录](COPILOT-RELEASE-VERIFICATION.json) 保留来源和各资产摘要，未改宽数据或发布校验器。

匿名公开查询与实际校验清单下载通过。核验时较新的 preview.16 已公开，两个芯片从 preview.12 正确选到 preview.16，同版不提示；已确认 preview.16 源码包含本轮提交，四份 Copilot 适配文件与 preview.15 相同。Windows latest 保持 v0.3.13。本次未升级、重开用户工具箱或在其安装内导入合成聊天，用户使用自动更新自行升级。原生恢复不等于用户桌面人工显示/滚动和付费下一轮全部验收。

| 架构 | DMG 大小（字节） | SHA-256 |
| --- | ---: | --- |
| arm64 | 23460919 | `a88b5be282a713d99f2fadc348bb41e8a01ffb82b83cd673cec58eb281128b4a` |
| x86_64 | 24856078 | `b308d842af482a1764edf4546633a8659476a58eaefc118c14f11a1fb62fa3ff` |


## 2026-10-16：preview.14 已发布，自动检查无返回恢复

用户实际版本为 preview.12，要求无需点击检查就提示下载。匿名公开查询与严格安装包选择能从 preview.12 识别当时的 preview.13，不能把用户现象直接归因于错误版本或发布未完成。旧 UI 对一直不返回的 workspace_info/check_update 无超时，初始化/检查标记会一直占用；两个新增合成桥测试在旧脚本均失败。preview.14 增加 10/30 秒恢复并沿用失败退避，迟到响应不能撤掉新提示。修复后本机 20 项 Mac 界面、56 项路径/更新单测全通过。

安装包与标签源码 `9a4626188bab5a7f63750ce7352de1a2384554a4`。[原生构建](https://github.com/feifeigong/ai-first-tools/actions/runs/38896558707) 两架构均通过原有共享与原生历史检查，冻结资源 7、Cocoa 页面/桥/自动提醒 9、系统 HTTPS 3、更新交接 9 项全通过。自动提醒使用合成发布响应，确认无需点击检查即可见下载按钮且未自动下载；更新审计仍验证真实窗口点击、桥排空、父进程自然退出、helper 替换与两次重开。

[独立核验](https://github.com/feifeigong/ai-first-tools/actions/runs/38898129754) 分别下载原构建与草稿全部 11 个资产，名称、字节、SHA-256、不可变标签及原生报告一致后公开 [preview.14](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.14)（发布 ID `414919247`）。本机核对八份原生报告全部通过；匿名公开列表确认两架构 preview.12 选择 preview.14、同版无提示、所有公开 digest 一致，实际下载公开校验清单核对摘要；Windows 最新稳定版仍 v0.3.11。

| 文件后缀 | 大小（字节） | SHA-256 |
| --- | ---: | --- |
| `arm64.dmg` | 23450742 | `96f1e9dfaedc9b7fda066b7350ab7623e733ea79cbbb44990ebacbca0addb317` |
| `x86_64.dmg` | 24845419 | `4f4f38904d3cd94c4ab6dff999a4fa610fa2c661fa7d36d91a6ba05f9360da6d` |

未操作用户 Mac，不能断言上述已复现的代码缺口就是其设备根因，或把 CI 自动提醒当作用户 preview.12 的实机验收。新包不会自行修改已卡住的旧程序。没有放宽 TLS、来源、哈希、格式或交接保护，没有读取真实聊天或请求在线模型。

## 2026-10-16：preview.13 已发布，Copilot Desktop 读取与搬出

新增只读 Python 事件适配，沿用已有原生迁移引擎。Windows 本机 122 项后端检查通过，包含 16 项 Copilot 专项与六个实际目标的 125 轮合成历史导入、完整正文回读、工具结果与源字节不变检查。[Windows CI](https://github.com/feifeigong/ai-first-tools/actions/runs/38880176012) 的 122 项后端（无引擎步骤明确跳过 1 项原生导入）、31 项共享界面、WPF 构建与 62 项外壳自检通过；Copilot 原生导入另已在本机和两种 Mac 架构执行，未将跳过当作通过。

已公开 [preview.13](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.13)，不可变源码标签固定为 `249684ec97e651ec7f47267df266f20fd0434eed`。[原生构建](https://github.com/feifeigong/ai-first-tools/actions/runs/38880176034) 的 arm64、x86_64 各通过 120 项共享/隔离来源及目标检查、10 项原生分页与本机模拟续聊检查，冻结资源 7 项、Cocoa 窗口与桥 9 项、系统 HTTPS 3 项、完整更新 9 项均通过。[独立核验](https://github.com/feifeigong/ai-first-tools/actions/runs/38881699858) 重新下载同次构建与草稿的全部 11 个文件，精确名称、大小、SHA-256 和标签源码完全匹配后公开（发布 ID `414778390`）。匿名生产更新选择在两个架构从 preview.12 选到 preview.13，同版不提示；公开 SHA 清单下载摘要与核验报告一致。

不读取用户真实 Copilot 记录/凭据，不发模型请求；不将隔离原生引擎回读称为用户真实 Copilot 样本、所有目标的桌面人工显示或付费续聊验收。适配字段、共享会话标注、未支持的撤回/截断和 VS Code 范围见 [COPILOT.md](COPILOT.md)。保留先前全部历史兼容与更新修复。

前一版 [preview.12](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.12) 于 2026-10-16 08:07:50 UTC 发布，窗口交接修复、原生按钮更新与资产核验见下方“preview.12 发布证据”；历史记录继续保留。

2026-10-16 用户再次报告校验转圈后，确认当时实际运行版本仍为 `preview.8`，且无步骤/秒数，原提示已与旧版源码核对。当时尚未确认安装 preview.10，未将此反馈作为新版失败或用户真机已通过的证据，后续请用户手动替换；用户随后确认已安装 preview.10，新的导入回归见下方。旧版当次系统阻塞的具体原因仍未知。

## 2026-10-16 preview.12 已发布：8/8 后窗口和取消均无响应

用户此前已确认安装 preview.10，本轮软件内更新时报告“正在释放安装包（8/8）、已用时 15 秒”不再变化，并确认取消和窗口均卡住。没有取得其系统线程栈，不能断言其当次 hdiutil 阻塞或已确定完整设备根因，更不能重新要求用户证明是否仍为 preview.8。

在修改前新增两个隔离回归，均失败：慢 helper 启动期间 update_status 被 apply_update 的状态锁阻塞；页面在等待 apply_update 返回时仍显示精确的“8/8、15 秒”。锁定 pywebview 的桥使用单独线程执行 API，再同步 evaluate_js 返回结果；Cocoa 关闭会删除视图，因此 API 自身先关窗再返回还存在返回/关窗竞争。修订为 apply_update 立即发布 starting 状态并返回，由后台启动 helper；不持有状态锁等待进程。页面先显示启动步骤，排空在途更新请求，再通过 pywebview 不需要 JS 回信的异步 callback 关窗。启动失败收回本次 helper、恢复可重试状态；完整性、版本、架构及搬运退出保护保留。

旧冻结审计直接调用 prepare/start_helper，绕过真实窗口点击和父进程退出，覆盖不足。新审计启动隔离签名 APP 的 Cocoa 窗口，经真实 JS/Python 桥点击检查/下载更新，要求八步、请求排空、原生窗口关闭和父进程自然退出，再验证实际 helper、原子替换、备份、新版 Cocoa 重开和再次独立重开。公开暂存也要求三个新增检查，不接受仅有旧六项的报告。下载使用隔离合成 DMG 替身；系统 HTTPS 单独保留。两架构运行结果和独立发布核验均已通过；隔离原生通过不是用户设备的实际验收。

### preview.12 发布证据

[公开下载](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.12)，2026-10-16 08:07:50 UTC 公开。不可变标签和安装包源码为 `553584b7bca40f13c1f0aaee2713fb82ba1d17f6`；后续文档提交不重做二进制。[同批两架构原生构建](https://github.com/feifeigong/ai-first-tools/actions/runs/38861141937) 首轮完成：arm64、x86_64 各 104 项共享/隔离检查、10 项原生分页/本机模拟续聊检查通过，含 preview.11 的缺少工具返回回归。冻结资源 7 项、Cocoa 页面/桥/自动提醒 9 项、系统 HTTPS 3 项、完整窗口更新 9 项均通过。

两份实际 update-test 报告均为 passed=true，九项 preparationStages、nativeUpdateClick、bridgeDrained、nativeParentExit、replacement、nativeRelaunch、backupPreserved、version、repeatNativeRelaunch 全 true，父进程和 helper 返回码均为 0，phase=complete，handoffFailure=null。此次从真实冻结 Cocoa 窗口经 JS/Python 桥点更新，验证八步、消息排空、旧进程退出，再执行 helper 原子交换、备份、新版原生重开及再次独立打开；没有用启动返回码或无窗口的 helper 测试代替交接。

[独立发布核验](https://github.com/feifeigong/ai-first-tools/actions/runs/38871513085) 单独下载原 CI 与草稿的全部 11 个文件，源码标签、名称、大小及 SHA-256 完全一致后公开（发布 ID `414696669`）。本地另下载八份小报告，逐个核对 digest 与检查项。匿名公开入口实测两个芯片从 preview.1–11 均选到 preview.12，同版不提示，公开 SHA 清单一致。[Windows 回归](https://github.com/feifeigong/ai-first-tools/actions/runs/38861141802) 的 106 项后端、30 项界面、WPF 构建及自检全部通过，Windows 公开安装包仍为 v0.3.8。

未读取真实对话/认证，未请求在线模型，也未操控用户实际 Mac。下载传输仍用隔离合成 DMG，系统 HTTPS 检查另行保留；不称为用户公网完整升级。已卡住的旧窗口不能靠发布自动改写，确认无搬运任务后仅关闭工具箱，再用完整 DMG 替换到 preview.12。保留源、旧副本、备份与全部历史兼容修复；用户设备的实际恢复仍待新版运行结果。

| preview.12 文件后缀 | 大小（字节） | SHA-256 |
| --- | ---: | --- |
| `arm64.dmg` | 23309337 | `297709a025e21e3280e4ff4291e6f910fd07001e258f7af9541aaf63039e115d` |
| `x86_64.dmg` | 24836896 | `50f4c7121fdf9c8f6f256136430157a78438b80858d027ca5be9aa8be6dfd2bd` |

## 2026-10-16 preview.11 已发布：修正缺少工具返回导致整条导入失败

上述手动安装之后，用户确认现在是 preview.10，单条 Cursor → 本机 Work 的明确错误为“历史工具调用缺少配对结果，已停止导入”。已确认属于 preview.9 引入的过严检查回归；此前测试只有完整配对，不能据此证明兼容被取消/中断的历史。

新增实际隔离 Cursor 数据库往返测试，在修复前对超长名称和补丁分别复现失败，修复后两类及完整/缺失返回混排均通过：原生两条一页读取，逐字核对历史说明；实际 exec resume 只连 127.0.0.1 模拟 Responses 服务，接收内容与文件一致，无真实认证或在线模型。保留源哈希、完整参数/已有结果、首尾正文、工具不重新执行的检查。孤立结果、跨轮编号重用、同轮重叠编号另有格式回归；类型不匹配、未知格式和完整性错误仍拒绝。旧 85 字符拒绝复现与修复检查继续保留。

preview.11 将无法确定配对的日志无损转换为明确的历史说明，原 payload 同时保留于外层元数据；没有把非法工具请求直接交给接口，没有伪造结果。结果显示日志说明数量；全部失败不再写“复制完成”，错误可换行选择复制。格式为 paginated-import-v3，允许旧格式一次新副本，旧数据和源保留。本机后端 101 项、完整 UI 28 项及原生分页/模拟续聊 23 项通过；两架构运行包和独立发布核验已完成，范围见下方。

### preview.11 发布证据

[公开下载](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.11)，2026-10-16 06:09:43 UTC 公开。不可变标签和安装包源码均为 `3d5d0acfea8236010fda4cd0e78a616dfc71a010`；后续文档提交不重做二进制。[同批两架构原生构建（attempt 2）](https://github.com/feifeigong/ai-first-tools/actions/runs/38835220696/attempts/2) 各 99 项共享/隔离检查、10 项原生分页及本机模拟续聊检查通过，包含本轮 Cursor 缺失工具返回和混排回归。冻结资源 7 项、Cocoa 页面/桥/自动提醒 9 项、系统 HTTPS 3 项、更新准备/原子替换/备份/重开/再次打开 6 项全通过。

首轮 M 系列全部通过；Intel 导入、分页、续聊及冻结窗口均通过，但系统 hdiutil 创建更新审计的隔离临时镜像返回 1，尚未进入更新替换检查，未生成 update-test.json，也未生成公开 DMG。具体系统原因未取得，不称为已确定的系统抖动。该次命令失败及运行记录见 [attempt 1](https://github.com/feifeigong/ai-first-tools/actions/runs/38835220696/attempts/1)，失败产物未发布；源码和检查标准不变的完整第二轮两架构通过后，才采用第二轮同批原资产，没有混用首轮包或跳过更新检查。

[独立发布核验](https://github.com/feifeigong/ai-first-tools/actions/runs/38837012077) 单独下载原 CI 和草稿的全部 11 个文件，比对源码标签、名称、大小与 SHA-256 完全一致后公开（发布 ID `414447025`）。匿名公开选择实测两个架构从 preview.1–10 选到 preview.11，同版不提示，公开 SHA 清单核对通过。[Windows 回归](https://github.com/feifeigong/ai-first-tools/actions/runs/38835220494) 的 101 项后端、28 项 UI、WPF 构建和自检通过；Windows 公开安装包仍为 v0.3.8。本机另以隔离目录和关闭 Windows 登记目录回退的测试入口运行 19 项目标登记/回滚用例：17 项通过，两项真实已安装 schema 用例明确跳过，不当作真机通过。

用户已确认 preview.10，可以软件内更新到 preview.11，再重新搬之前失败的记录并打开新副本；工具日志的历史说明数量不等于失败对话数量。不修改源或旧副本，不发在线模型请求，也未操控用户真实 Mac。Mac 更新审计的下载传输仍用隔离合成资产本地替身；未冒称用户公网完整升级或真实账号续聊已验收。

| preview.11 文件后缀 | 大小（字节） | SHA-256 |
| --- | ---: | --- |
| `arm64.dmg` | 23296918 | `fe29885dcfadcd08b67597aa91ff2c6a02da4c9de2d8841347c56465f0214431` |
| `x86_64.dmg` | 24829529 | `0e90dca0fa077d7dd44e3ca54d587dde75bab09cec17bb4e9d251d84d7669f3c` |

## preview.10 候选失败记录（失败包未发布）

28f808d 的 [38726399032](https://github.com/feifeigong/ai-first-tools/actions/runs/38726399032) 未通过，未创建公开标签或资产。ARM 准备八步通过，更新后的页面仍未加载，说明提前挂载视图不足以解决；Intel 在原生分页检查后的临时目录清理遇到默认插件后台 git 写入。随后隔离测试显式禁用 plugins，应用重开改为系统 LaunchServices。仍需两架构真实窗口、更新重开及再次打开的全部检查通过，不能用启动器返回码替代应用自己的报告。

fcc4742 的 38727438948 ARM 仍在更新重开未加载，且 nativeContentAttached=true、localhost=200，LaunchServices 未解决问题，撤回该启动方式以保留对子进程的直接等待和停止。只在隔离 smoke 中添加 Cocoa 导航观察器，记录导航阶段、错误域/编号和异常类型，不记录 URL、请求头、环境或用户记录；先取得更具体的失败证据，不把待验证假设算成修复。

cf80b47 的 [38728521782](https://github.com/feifeigong/ai-first-tools/actions/runs/38728521782) ARM 报告明确记录 policy → policyReturned → started → provisionalFailure，错误 NSURLErrorDomain / -1001；同包首次窗口正常且原生 Python 读取 loopback 页面返回 200。它确认本次失败为 WebKit 页面请求超时，不能据此确定用户设备原先校验等待的系统原因。后续候选改用 WKWebView.loadFileURL:allowingReadAccessToURL: 直接读取安装包中的 ui/index.html，读取范围仅限该 ui 目录，不再启动页面 HTTP 服务；Python 原生桥、业务和更新 HTTPS 不改。新增 bundledFileNavigation 真实检查，仍待双架构原生窗口/更新/再次启动结果，不将单元模拟当原生通过。

## 2026-10-14 preview.6 自动检查与桥就绪（历史已发布）

[公开下载](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.6)。构建源码 `9703d4335043526fe3ad0ecb00fdba6e31b83ac4`，同名 Git 标签指向此提交；后续交接文档不重做包。

用户确认当前安装 preview.2：手动检查能看到新版，启动却没有提醒。复查实际标签源码发现，自动查询失败只在手动模式显示错误，preview.2 又只尝试一次；preview.3/4 同样隐藏自动错误，仅在六小时后再查。存在这些代码缺陷并不证明已确定用户 Mac 当次失败是 DNS、超时或代理问题，没有读取其电脑日志。

- 用合成 API 重现结构化网络失败、桥异常静默以及短时间不再检查：修复前两种失败的通知断言失败，自动重试断言超时；不是将未检查到误报为最新。
- 修复后首次失败显示非阻塞的「将自动重试」；普通错误按 1/5/15/60 分钟退避，持续错误最多每小时一次；GitHub 限流直接等一小时。成功后恢复六小时检查，手动成功取消旧重试；用户关闭错误提示后继续后台检查但不反复弹提示。下载/更新中延后版本查询，不重入安装。
- 定向浏览器 7 项及追加 2 项均通过，包含两种自动错误、限流、退避/关闭提示、手动查询替换待重试任务、下载中延期，以及既有单次点击/等待搬运/取消/布局。这里只测共享页面合成 API，没有运行作者 Mac 或访问 Agent 数据。
- preview.5 源码 `6fe261b` 的首轮两架构构建 38496236792 全部通过，11 个草稿资产与独立下载产物匹配；但同源码重复构建 38496246060 的 Intel 在首个 Cocoa 窗口检查失败，pageLoaded=false、桥注入开始、localhost 页面 200，两条 API 回复线程等待就绪标记超时。它不是更新替换阶段的故障。故 preview.5 不公开，不能用首轮绿色忽略重复失败，也不移动已创建标签。
- 检查锁定 pywebview 源码发现其页内 ready 事件在 Python 就绪标记设置前派发；两套 UI 都在该事件里立即请求 Python API，存在时序竞争。preview.6 改为等待原生 loaded 后显式发送 ai-first-ready，Cocoa 初始化与启动版本查询在此信号后进行；Windows 路径不等待此信号。合成桥未就绪时两个 UI 均不得调用 API 的用例先失败，修复后通过。此证据确认安全时序缺口，不断言已掌握该 Intel 当次卡住的全部框架原因；后续两轮原生复测均通过。
- 本地 49 项定向测试通过（10 项页面、39 项共享/更新器），另完整 21 项共享页面检查通过。实际 Mac 由 [发布资产所属运行](https://github.com/feifeigong/ai-first-tools/actions/runs/38497770696) 和 [同源码重复运行](https://github.com/feifeigong/ai-first-tools/actions/runs/38497781070) 检查：两次的 arm64、x86_64 各 74 项共享/隔离单测通过，四组冻结 APP 的 7 项资源/引擎、5 项 Cocoa/WebKit/桥、3 项真实 HTTPS、4 项 helper/原子交换/备份/重启全部通过，资源封印与 DMG 校验通过。
- 发布使用 38497770696 的同批两个架构，不混用重复构建。暂存日志确认实际上传；独立下载后逐一核对 11 个上传资产的标签、版本、架构、报告、长度和 SHA-256 digest，全部匹配后公开。首次下载原产物的本机传输停滞，仅停止本任务的下载进程并有时限重试成功，没有关闭 TLS 校验、修改全局网络或停止用户软件。
- 发布后匿名公开列表的生产选择逻辑确认两架构 preview.2/3/4 都选到 preview.6，同版本不提示；实际下载公开校验文件并核对 DMG 条目。生产 Windows 选择仍只将 v0.3.7 升到 v0.3.8、不选 Mac 标签，并核对先前下载的公开安装包。这些公网检查在 Windows 宿主执行，不冒称用户 Mac 的实际完整升级。
- [Windows 回归](https://github.com/feifeigong/ai-first-tools/actions/runs/38497770629) 通过 76 项后台、21 项浏览器和工具箱自检，WPF 零错误/警告。没有修改已公开 Windows v0.3.8 资产；Mac preview.5 保持未公开，不移动旧标签或替换已公开包。
- 原生更新检查仍是临时 APP 副本、合成旧版本元数据和实际 helper/Cocoa 重启，不是从已发布旧二进制在作者安装目录手点公网升级。未读取真实 Agent 对话/认证或发送模型请求。preview.1/2 需最后一次手动换到本版；preview.3/4 可以软件内更新。Finder/Gatekeeper、macOS 13/14、用户具体网络与第三方实际显示/续聊仍待实机验收。

| preview.6 文件后缀 | 大小（字节） | SHA-256 |
| --- | ---: | --- |
| `macos-arm64.dmg` | 23273872 | `2aefcfeb18f348f7186543009cd9a6d8c27b0591bbecf808ba9439870b5e37e2` |
| `macos-x86_64.dmg` | 24763822 | `d124c28608e00fd66bf3e5b4e9f8342ea20db5a6716e2865f38b43d988d53291` |

## 2026-10-13 preview.4 一键更新与重启修复（历史已发布）

[公开下载](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.4)。构建源码 `7dcc96f9f77c9b1a2bd714560521ef0b1dc64756`，Git 标签指向同一提交；文档提交不重做二进制。

- [发布资产所属运行](https://github.com/feifeigong/ai-first-tools/actions/runs/38357964353) 与 [同源码重复运行](https://github.com/feifeigong/ai-first-tools/actions/runs/38357970395) 均成功，两次的 arm64、x86_64 各 73 项共享/隔离原生单测通过。四组真实 macOS 15 冻结 APP 都通过 7 项资源/引擎、5 项 Cocoa/WebKit/桥、3 项真实 HTTPS、4 项更新检查以及 ad-hoc 封印和 DMG 格式校验。
- 本次发布使用 38357964353 的两个架构，不混用重复构建的二进制。该运行的 stage-release 日志确认实际上传，而非跳过；发布前独立下载原产物，核对标签、四类报告和 11 个上传资产的大小及 SHA-256 digest，全部匹配后公开。
- 两架构实际执行冻结 helper、交换前自检、系统原子交换、保留旧 APP 备份、新版 Cocoa/WebKit/Python 桥重启及版本确认；报告 helperReturnCode=0、receipt/preflightReport=true、五项 relaunchChecks=true。使用临时 APP 副本和合成旧版本元数据，不是从已公开旧二进制在作者安装目录手点升级，也未实际执行 Mac 原生整包公网下载/挂载的完整更新回路。
- 针对 preview.3 后续重启失败，保持系统 HOME 的审计修订仅使 ARM 复测通过，Intel 仍失败。检查锁定 pywebview 6.2.1 Cocoa 实现后推测共享数据异步清理与页面加载竞争；本版避开该清理路径，保留随机本机端口、系统 HOME 和严格 HTTPS，增加两项回归，重复原生构建通过。未取得全部系统错误诊断，不把推测当成已证明所有平台行为。
- 发布后用匿名公开 GitHub 列表运行生产选择/完整性逻辑：两架构 preview.3 和 preview.2 都选择 preview.4，preview.4 不提示同版本；实际下载公开校验文件并核对 DMG 的 digest/大小要求及哈希条目。此检查在 Windows 宿主运行纯 Python 逻辑，不冒称 Mac 冻结 APP 的用户公网完整升级已经验收。
- [本源码 Windows 回归](https://github.com/feifeigong/ai-first-tools/actions/runs/38357964354) 通过 75 项后台、15 项浏览器与工具箱自检，WPF 构建零错误/警告；未重新发布 Windows 包。Windows 安装/下载证据见 UPDATER-QA.md。
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
- 两架构 ad-hoc 资源严格校验、DMG 格式、下载后的 SHA-256 核对通过。CI 只把报告通过的同一运行资产暂存到匹配版本草稿，独立下载后再核对 9 个上传资产的大小和 digest；最终公开前仍需人工确认，不覆盖已发布版本。[Windows CI](https://github.com/feifeigong/ai-first-tools/actions/runs/38344666214) 通过 60 项后台、13 项浏览器及工具箱自检/构建（零警告/错误）；本次没有重发 Windows 安装包。
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
- 新工具箱浏览器布局/完全隐藏侧栏/更新提示：1 项，960–1440 宽度。
- 既有导入测试：19 项通过，另 2 项 Mac 原生测试在 Windows 明确跳过。
- Windows 工具箱自检：62 项通过，构建零错误/零警告。
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
## preview.8：自动提醒专项（历史发布）

[公开下载](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.8)，发布 ID `412665873`，2026-10-14 12:22:52 UTC 公开。源码标签固定为 `5e669f20af6b19c808889e4d4c320fbd4740200d`。

- 新增四组隔离浏览器测试先在旧实现复现失败（六个事件子场景）：持续打开后来有新版、返回窗口/在线恢复/页面可见、初始化暂时失败、已发现更新后网络失败与关闭提示。
- 修复后上述用例通过；继续检查限流退避不被焦点/联网事件打断、并行请求被阻止、下载中不额外查询、同版不重复弹提示。本地 83 项共享检查通过，其中 3 项 Mac 专用原生导入明确跳过，待 Mac runner 检查；26 项浏览器检查通过。
- 原生冻结 Cocoa 审计增加自动查询后可见按钮、未经点击不下载。响应明确为合成版本，既不读取真实 Agent 数据，也不依赖 GitHub 是否恰好有一个新版本。
- 主分支原构建 `38560496836` 两架构各 83 项共享/原生导入检查、3 项完整原生历史分页检查通过；实际冻结包资源 7 项、Cocoa 窗口/桥/自动提醒 7 项、HTTPS 3 项、更新安全替换与重开 4 项通过。Stage 实际上传 11 个文件；独立下载此构建的两架构原资产，逐个核对全部报告、上传文件大小/digest 和不可变源码标签后公开。标签构建 `38560504847 / attempt 2` 两架构完整复测同样通过，其产物没有混入公开包。
- Windows 两次源码回归 `38560496850`、`38560504866` 成功，不重发 Windows v0.3.8。所有测试仍使用隔离合成数据，不发模型请求、不访问真实登录与对话。
- 用户 Windows 搬出问题仅记入 KNOWN-ISSUES.md，未修复、未实机复现。

**保留失败记录：** 标签构建首轮 ARM 在更新后原生重开时 WebKit 页面加载超时，`windowShown=true / pageLoaded=false / bridgeInjectionStarted=false / localPageStatus=200 / localPageBytes=5610`，更新审计失败并回滚，未生成或发布该 DMG。首次窗口与自动提醒、网络、历史测试通过，不是把提醒失败改成成功；没有放宽原生检查。主分支原构建和标签完整复测通过，但不据此宣称已经消除所有偶发 WebKit 启动失败。

| preview.8 文件后缀 | 大小（字节） | SHA-256 |
|---|---:|---|
| macos-arm64.dmg | 23,280,029 | `1ad322afcd37b7e27a38755076a9a89b36d69d429d38bbedddb40a479cd7457c` |
| macos-x86_64.dmg | 24,764,103 | `88ec23390eb865cf79e0858fee2f77dad4e1d93dd821b81e7a8611891f96d482` |

公开后用无认证生产选择逻辑验证两架构 preview.2/3/4/6/7 均选到 preview.8，同版不提示；实际下载公开 SHA 清单并核对架构 DMG 条目。没有在用户实际 Mac 上做旧安装程序的公网完整升级、休眠后窗口恢复或手动点击验收，不能把浏览器事件测试/冻结合成提醒说成这些已经完成。旧版本内部的调度只有在升级后才改变。

## preview.7：长对话分页专项（已发布，历史记录）

[公开下载](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.7)，发布 ID `412440705`，2026-10-14 08:09:00 UTC 公开。源码标签固定为 `12aa483b9191ee4772cbfaa288dd9429a23f047f`，文档补充不重做运行包。

发布包来自主分支构建 `38527937388 / attempt 2`：两架构各 80 项共享/格式检查、3 项原生历史分页检查，冻结资源 7 项、Cocoa 窗口/桥 5 项、实际 HTTPS 3 项、更新 helper/安全替换/原生重开 4 项通过；实际 Stage 上传 11 个资产，全部独立下载原 CI 资产并对照 GitHub 上传大小与 digest。标签构建 `38527943205` 同源码两架构检查也通过。Windows 两次源码回归成功，本地 85 项共享+原生检查和 21 项浏览器检查通过；隔离 19 项旧导入回归通过，2 项「读取已安装个人数据库结构」因不读取真实数据库而跳过。未重发 Windows v0.3.8。

**保留失败记录：** 主分支首轮 Intel 的搬家分页、初次窗口和 HTTPS 检查通过，但更新后 Cocoa 重开页面加载超时，`windowShown=true / pageLoaded=false / bridgeInjectionStarted=false / localPageStatus=200`，更新审计回滚且为失败，未生成/发布该 DMG。没有放宽检查或改动无关 UI 来掩盖问题；相同源码的标签构建及主分支完整复测通过。这里只证明发布批次通过，不保证用户设备没有偶发 WebKit 启动失败。

| preview.7 文件后缀 | 大小（字节） | SHA-256 |
|---|---:|---|
| macos-arm64.dmg | 23,277,144 | `73aa4075403786bae352525fc64cf32757ec988cb0cb735d8d3c9459caa1e7a2` |
| macos-x86_64.dmg | 24,763,337 | `518d39c0a80192c16f982424b73d8acac6272280db85372223730ab8455f0e58` |

公开后，在 Windows 宿主用无认证生产选择逻辑确认两架构 preview.2/3/4/6 都选到 preview.7，同版本不提示；实际下载公开 SHA 清单，核对架构 DMG 条目。不是用户 Mac 上的真实完整更新/界面人工测试。

旧测试仅验证短正文整体回读，漏掉了桌面端逐条分页。新增隔离原生用例先复现 legacy 历史的 `thread/items/list` 报不支持；修正后验证 paginated 记录及索引由目标引擎自然加载。

- 125 轮真实 Cursor 结构合成数据 → 搬家 → 原生 Work，倒序 17 轮一页直到首轮，正序 19 条一页直到末条；250 条正文逐条精确比较、多行长文本、唯一 ID、单条锚点；Cursor 数据库字节校验不变。
- 短正文 Work/Codex 两种模式：列表、模式标记、原生读取/恢复。
- 混合正文：两轮、思考、三次重用工具调用 ID、三份工具结果；逐条历史无丢失、工具结果不产生伪用户轮次。
- 六个纯单元用例覆盖完整性（前/中/后/重复文本/顺序）、格式拒绝、稳定编号/ordinal、旧去重允许安全重搬、失败不登记且仅清理新副本。
- Mac 两架构 CI 使用官方 Codex 0.162.1（固定 SHA），全为隔离数据，不登录、不发模型请求；该测试引擎不进入 DMG。
- 未在用户真实 Mac 上手动滚动 ChatGPT；未验证付费下一轮、全部来源 × 目标组合。不能把本节原生协议验证宣传为这些检查已经通过。

## 2026-10-15：Mac 迁入历史的续聊长度限制（preview.9 已发布）

- 用户已确认错误出现在发送下一条消息后。preview.7/8 验证分页和回读，没有覆盖真实续聊请求中历史工具字段的长度；不能据此说续聊已通过。
- `codex_import.py` 在生成分页历史前，为超长/非法工具名称和调用编号建立稳定的兼容映射，调用与结果成对，重复编号分配唯一别名；合法名称预先保留，避免别名碰撞。原字段保留在记录的 `dialog_mover_original`，正文、思考、参数与结果不截断；配对缺失/类型不符停止导入，不放宽格式检查。
- 导入格式升为 `paginated-import-v2`，旧成功记录允许创建一次新副本，之后恢复去重；不自动修改源或用户已经继续聊过的旧副本。
- 新增 `test_codex_replay.py`：隔离合成 Cursor 数据库 → 实际搬家 → 原生引擎 `exec resume` → 仅监听 127.0.0.1 的模拟 Responses 服务。关闭兼容映射时，85 字符调用编号/工具名分别复现同样的 400 长度拒绝；开启后普通、超长、重复编号和自定义补丁的五类测试通过，补丁不重新执行，参数/结果完整，源不变。全程不使用真实认证、不请求在线模型。
- 本机 92 项共享/格式/原生分页、26 项界面及 5 项续聊检查通过。Mac 两架构各 87 项共享、8 项原生分页/续聊及四类冻结检查通过；发布包取 `38691055276 / attempt 2`，源码标签固定 `12391ab6431a9f2cbc77b5650aec51ad9bc925c2`。独立发布核验 `38693214923` 下载并逐个比对原 CI 与草稿的全部 11 个文件、大小和 SHA-256，通过后公开 preview.9（发布 ID `413485163`）。首轮 ARM 更新后页面未加载的失败报告保留，未发布失败产物；细节及真机验收边界见下文。
- Windows 普通 Chat 搬出问题仍仅记录，不重发 Windows 安装包；本轮未更改更新请求频率或 GitHub 限流机制。

[公开下载 preview.9](https://github.com/feifeigong/ai-first-tools/releases/tag/v0.4.0-macos-preview.9)，2026-10-15 06:35:55 UTC 公开。[两架构原生构建及完整复测](https://github.com/feifeigong/ai-first-tools/actions/runs/38691055276/attempts/2) · [独立下载发布核验](https://github.com/feifeigong/ai-first-tools/actions/runs/38693214923) · [Windows 源码回归](https://github.com/feifeigong/ai-first-tools/actions/runs/38691055256)。冻结检查包括资源 7 项、Cocoa 窗口/桥/自动提醒 7 项、HTTPS 3 项、更新替换与原生重开 4 项；不是在用户的真实 Mac 上操作。

| preview.9 文件后缀 | 大小（字节） | SHA-256 |
|---|---:|---|
| macos-arm64.dmg | 23,116,104 | `92946d3950eed4bb2fee1916a9dd9c10222f2f3282c48bfbd4d1882c0284be16` |
| macos-x86_64.dmg | 24,767,927 | `f6c4ce49834feee1ec96c9d793e0304b2f9b182ea33b2be71a30b4345b08975e` |

**保留失败记录：** 原构建首轮 ARM 更新后原生重开超时，`windowShown=true / pageLoaded=false / bridgeInjectionStarted=false / localPageStatus=200 / localPageBytes=5610`；首次窗口、分页、续聊和网络检查通过，更新检查保留失败，未生成或发布 ARM DMG。Intel 首轮通过，但公开包只取同源码完整第二轮两架构的成功产物，不混合轮次。没有修改 UI、延长超时或放宽断言来让此项通过，不据完整复测断言既有偶发 WebKit 启动失败已全部消除。

发布核验与应用构建分开：本地下载构建产物超时，新增独立的 CI 下载比对步骤，读取原构建的两架构产物及草稿全部资产，核对轻量标签源码、四类原生报告、精确文件名、大小和 SHA-256。`38693088630` 首轮核验在草稿按标签查询时失败（GitHub 此接口未返回未公开草稿），草稿未公开；改为认证发布列表中精确匹配唯一标签后，`38693214923` 完整核验通过。此流程修订不重做运行包，不移动源码标签；11 个发布文件均来自上述第二轮构建。

公开后，无认证生产选择逻辑在两个架构从 preview.1–8 均选到 preview.9，同版不提示；实际下载公开 SHA 清单并核对其摘要。Windows v0.3.8 的三项原资产仍在，Mac 版本不附 Windows 安装包。未测试用户真实设备的完整公网升级、界面手动翻页或账号发送下一条；不得把本机模拟 Responses 续聊说成在线模型验收。旧副本须重新搬入为新副本，升级不会自动改写原历史。

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

| preview.10 文件后缀 | 大小（字节） | SHA-256 |
| --- | ---: | --- |
| `arm64.dmg` | 23364390 | `9aa93b1d63e4c70f5d4b2bb64d2dfc51642f541e74e041e9c0294dedca1cf58d` |
| `x86_64.dmg` | 24828179 | `594a04b6403a0f7c8947aae67b1f298c22b7ee4136ec98eb6da46319a96edb76` |
