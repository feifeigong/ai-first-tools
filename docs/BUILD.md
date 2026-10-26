# 开发与构建

2026-10-24压缩项目修复：独立增量构建须显式传最新 `--base-package artifacts/codex-program-preview/package --build-directory artifacts/chatgpt-project-history-checked --output <新独立目录>`，避免回退重置组件。搬家spec新收集zstandard==0.23.0并补充许可证；保留其他工具的原许可证。冻结兼容门槛现为7项（含压缩列表/完整导出/损坏保护及Windows扩展路径），原智能15项、现有WPF全部通过后才交付。C盘无空间时将本轮TEMP/TMP/PYINSTALLER_CONFIG_DIR指向D盘独立构建目录，不清理用户文件。实际结果见CODEX-SOURCE-QA.md。

2026-10-23 Cursor → ChatGPT 历史可移植性修正（未证明解决第二轮续聊）：`scripts/build_codex_compat_preview.py --output <新的独立目录>` 仅重建搬家程序，继承已验证外壳/续跑/重置组件，核对未改动文件摘要，执行冻结兼容 5 项、智能搬家 15 项及 WPF 141 项后生成新的完整文件清单。`--codex-import-self-test <报告>` 不读取真实记录或请求模型。实现、验证边界及旧格式允许新副本的规则见 [ChatGPT 导入 QA](CHATGPT-IMPORT-QA.md)。

普通用户只需下载安装包。以下内容供开发者使用。

Mac 构建、完整背景和继续开发步骤见 [Mac 开发交接](MACOS-HANDOFF.md)、[开发背景](DEVELOPMENT-CONTEXT.md)。下面的 WPF/NSIS 命令仅适用于 Windows。

## 目录

- `workspace/`：WPF 单窗口工具箱。
- `dialog-mover/`：Python / pywebview 对话搬家界面与本机适配。
- `auto-resume/`：随工具箱冻结的续跑后台、原生组件锁定清单及回归测试。
- `txcript/`：修改后的 Rust 迁移引擎，保留上游许可证与文档。
- `installer/`：NSIS 当前用户安装程序，不要求管理员权限。
- `scripts/`：打包、许可证收集、发布包检查。

## 开发环境

智能迁移的本地开发预览可使用 `python scripts/build_memory_preview.py --output <独立交付目录>`，详见 [智能迁移说明](SMART-MIGRATION.md)。Windows 搬家程序冻结前先构建 `dialog-mover/记忆服务.spec`，将生成的 `AI一手记忆服务.exe` 放到 `dialog-mover/bin/`，再冻结原搬家程序；不得只复制旧版冻结搬家 EXE。`--memory-self-test <报告>` 使用隔离合成项目检查内置服务、中文检索、原文读取及撤销，不读取真实会话或请求模型。

Windows x64、.NET SDK 8、Python 3.13、Git。编译引擎需要 Rust 1.96 或更新版本、Visual Studio C++ 构建工具；网络读取特性还涉及 LLVM/libclang、CMake、NASM 等原生依赖，详见 txcript 上游构建说明。不要用未修改的上游 EXE 替代本项目引擎，否则国产 Agent 等适配会缺失。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r dialog-mover\requirements-dev.txt
cargo build --manifest-path txcript\Cargo.toml --release --locked -p txcript-cli
New-Item -ItemType Directory -Force dialog-mover\bin
Copy-Item txcript\target\release\txcript.exe dialog-mover\bin\txcript.exe
Set-Location dialog-mover
python -m PyInstaller --noconfirm --clean 对话搬家.spec
python -m unittest test_chatgpt test_imports test_close_safety test_embedded_startup -v
python -m unittest test_agent_icons test_import_ui test_ui_polish -v
Set-Location ..
dotnet build workspace\AIFirst.Workspace.csproj -c Release
```

界面自动检查默认使用已安装的 Microsoft Edge；测试文件使用合成记录。原生 Codex 专项测试需要本机对应程序，不要把它的“恢复成功”理解为已经发送模型请求。

## 打包发布

从 [NSIS 官方发布](https://sourceforge.net/projects/nsis/files/NSIS%203/3.12/) 获取便携编译器并解压，从 [微软官方](https://go.microsoft.com/fwlink/p/?LinkId=2124703) 获取 WebView2 bootstrapper。脚本会检查微软签名；不要使用不明来源的文件。

先运行 `python scripts/prepare_auto_resume.py`，按锁定的 OpenAI 官方 npm 发行包和 SHA-512 获取 Codex 原生组件；许可证与 NOTICE 按固定源码提交及 SHA-256 核对。进入 `auto-resume`，以 Python 3.13 执行 `python -m PyInstaller --noconfirm AI一手续跑后台.spec`。不提交 `bin/` 二进制或本机运行数据。冻结后台的 `--runtime-self-test <报告>` 只用隔离未登录目录、禁用工作的合成配置进行原生握手与启停，不请求模型。

```powershell
.\scripts\package.ps1 -Python .\.venv\Scripts\python.exe `
  -MoverPackage .\dialog-mover\dist\对话搬家 `
  -ResumePackage .\auto-resume\dist\AI一手续跑后台 `
  -AnalysisToc .\dialog-mover\build\对话搬家\Analysis-00.toc `
  -NsisDirectory C:\BuildTools\nsis-3.12 `
  -WebViewBootstrapper C:\BuildTools\MicrosoftEdgeWebview2Setup.exe
```

生成安装包、免安装 ZIP 与 SHA-256 校验文件，位于 `artifacts/release/`。工具箱以自带 .NET 的方式发布，迁移引擎旁也带所需 Visual C++ 运行库；原应用源码和引擎不因打包而改写。

Windows 流水线额外冻结内置续跑后台并执行原生离线检查；干净 runner 实际安装后，通过真实开关验证无外部运行环境时启停、禁止重新常驻、运行中覆盖更新与恢复、卸载后的进程和开机项清理。`audit_bundled_resume.py` 明确拒绝修改非 CI 用户安装；本机原生控制测试使用独立合成配置并隔离旧程序发现和注册表操作。

维护者可准备同版本草稿，手动运行 GitHub Actions 的 Windows release packages。流水线打包，在干净 runner 测静默安装/重复覆盖/自检/卸载和额外文件保护。全部通过后，把同名 lightweight Git 标签指向该次已验证构建提交；已有标签不得移动。暂存检查标签与构建 SHA 一致才上传到草稿，不自动公开。若仅末尾暂存失败，用 Stage verified release assets 输入 windows 与原 run_id，复用通过检查的原资产，不混入另一次构建。必须核对实际资产和日志，绿色但跳过不等于已上传。

当前只在 txcript 源码树与 v0.3.6 完全相同时复用其本项目原生引擎，并校验发布 ZIP 和 EXE 哈希；引擎源码有变化会拒绝复用，须编译、验证并更新此构建步骤，不能拿上游原版替换。NSIS 从官方镜像下载并核对固定长度与 SHA-256，防止下载到镜像 HTML；WebView2 bootstrapper 保持微软签名校验。

安装器只在当前用户的固定程序目录写入，运行时拒绝更新/卸载，不强制结束搬运。卸载按生成的文件清单逐个删除，不递归清空任意目录，也不删除用户新增文件或 Agent 历史。

v0.3.7 起打包脚本生成 `update-manifest.json`，逐个登记程序文件、大小与 SHA-256。不要在生成清单之后修改程序文件。安装包和 ZIP 均须与同次构建的 `SHA256SUMS.txt` 一起发布；GitHub 上传后还会提供各资产的 SHA-256 digest。发布操作与更新测试见 [UPDATES.md](UPDATES.md)。

Windows 暂存流程现同样执行 `verify_windows_release.py`：独立下载原 CI 和草稿文件，复查原始安装报告、不可变标签、精确文件名、大小及 SHA-256。报告通过后才公开；不混入本机重建文件。GitHub JSON 直接按 UTF-8 字节解析，避免 Windows 默认 codepage 无法读取中文发布说明。

发布前须检查源码和包中没有真实账户、记录、日志和私人截图，核对源程序/引擎哈希，执行安装、启动、更新保护、卸载保护和关键回归。没有 Windows 全新虚拟机验收时，不能宣称已覆盖全新系统。

v0.3.5 / v0.3.6 使用相同的既有已测试引擎，SHA-256：`799b80dff7ba44cb05f1a92ed5f64a4969ffefc5ad7b3566600ed88adaaaacd2`。

# 2026-10-23 本地预览启动修复补充

选择内置页使用 `--page dialog-mover` 或 `--page auto-resume`；`--tool` 保留完整自定义 EXE 路径用途，并兼容两个已知内置工具编号。名称不能被当作启动文件路径。不要仅依据工具箱主窗口句柄报告工具打开成功，应再检查实际工具页加载/内嵌握手。

单工具的 InvalidDataException/无效路径等预期启动失败在工具页处理，不触发全局工具箱退出。新增自检使用隔离配置和注入日志，不启动真实工具或读取真实聊天。当前修复构建证据位于 `artifacts/startup-guard-preview/`，源码阶段自检140项、最终包141项通过，0失败，清单与交付检查通过。完整搬家引擎、记忆服务、重复搬家修复、续跑与重置提醒组件不重建，逐文件摘要与上一包相同。不覆盖安装、不强杀任务、不提交或发布。

旧报错窗口已退出。使用正确的 `--page dialog-mover` 打开独立启动修复预览，启动握手报告 `opening-health.json` 为 ready=true、attached=true、error=null；随后通过桌面控制显示窗口，目视确认对话搬家页与软件列表已加载、没有异常弹窗。此为正常预览启动核对，没有点开真实聊天正文、执行搬家或发送模型消息，不能当真实迁移/续聊通过。

## 2026-10-23 智能搬家残留登记及 1.1.31 兼容修正版

上面的启动验证不代表智能搬家问题已经解决。用户再次反馈后，针对旧 workspace 会话仅剩编号、项目/工作区/对话目录消失的情况补齐兼容，同时精确适配官方已安装 1.1.31 静态规则中的 persistent_projects。保留旧行、资料与回执，正常入口优先复用；原生结构、未知规则、后续工作和撤销保护不放宽。

构建位于 `artifacts/memory-repeat-compatible-preview/`。源码96项回归与1项页面桥、冻结15项与WPF141项通过，只重建搬家程序，完整迁移引擎/记忆服务、续跑/控制和外壳程序逐文件摘要保持。冻结审计加了连接前隔离目录拒绝，首轮隔离遗漏如实记录在 SMART-MIGRATION-QA.md，失败包不交付。交付前更新完整文件清单、复查源码摘要和包内容；启动仍使用 `--page dialog-mover`，不自动测试真实聊天搬家、读取正文或发模型请求，不提交或发布。


## 2026-10-24 最新重置漏报修复预览

只重建 `workspace/AIFirst.Workspace.csproj` 的 self-contained win-x64 外壳，覆盖到 `artifacts/codex-compatible-preview/package` 的全新副本；不得覆盖正在运行的包。`tools/`、续跑控制脚本和目录清单逐文件摘要保持。更新 development-preview 源指纹，执行 --self-test、--render-reset-ui 及隔离 --check-public-reset-feed，最后生成完整清单并执行 check_release.py 后复制到新的独立预览目录。构建证据 `artifacts/reset-latest-preview/`，WPF142项、11份合成渲染与实际公开原帖核对通过。没有重新冻结搬家程序，不将这次重置修复称为用户第二轮报错已经解决。

## 2026-10-24 通用搬家程序兼容校验预览

可用 `scripts/build_codex_compat_preview.py --base-package artifacts/reset-latest-preview/package --build-directory artifacts/codex-program-preview --output <全新独立目录>` 在最新外壳上仅重新冻结搬家程序，避免回退最新重置修正。构建目录必须在artifacts内且尚不存在；交付目录必须是工作区之外的新目录。冻结兼容检查现要求6项，包含真实引擎的普通Cursor导入和两轮合成已保存问答回读；仍不请求模型，不称在线续聊通过。非搬家组件摘要及包清单检查保留。
