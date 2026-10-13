# 完整开发背景、产品决策与架构

本文件供作者、协作者和新的 AI 编程对话接手使用，记录决策和边界，不把旧设想当成已完成能力。

## 项目由来与演进

最初是「对话搬家」：复制不同 AI Agent 的历史，特别是 WorkBuddy、WorkBuddy AI、千问办公等国内软件与 Cursor、ChatGPT 本机任务之间的迁移。底层采用 txcript 的修改版，保留上游许可证和完整源码，新增国内适配、本机登记、导入报告和测试。

用户遇到过“生成文件但 ChatGPT 找不到记录”，因此不能只以文件存在判定成功。现在额外校验本机数据库结构、登记项目/模式/历史、备份并回读；格式变化直接拒绝，不强行写入。

ChatGPT 普通云端 Chat/Work 不可写，本机 Work/Codex 分开；Claude 普通聊天与 Cowork/Claude Code 分开。豆包本机轨迹不等于服务器正式会话，不能因为能生成某种文件就宣传原生搬入。

随后作者希望把自制工具集中到带 AI一手品牌的工作台，面向非技术读者。下载包应能直接运行，不要求读者拉代码、配置环境或理解内部进程。

## 固定的产品原则

1. 这是作者自制工具工作台，不是插件市场；不增加添加 EXE、管理插件、内部/外部打开入口。
2. 打开直接显示工具，一个窗口；切换保留状态，不让子窗口先闪出再拼接。
3. 用作者给定 AI一手 Logo 和已确认透明资源，不重新设计、不加白底外框。搬家外层/内层同一标记。
4. 用实际 Agent Logo；名称与版本/模式说明上下排列，ChatGPT 不用字母缩写代替。
5. 侧栏真正隐藏，展开/收起标记不同；鼠标不残留蓝框，但键盘 `focus-visible` 可见。
6. 简单中文步骤：选来源和记录 → 选目标/模式 → 选文件夹 → 确认。
7. 只复制，源记录保留；不迁移项目文件、附件、认证、模型权限、运行环境。
8. 搬运中不可强退/更新，异常必须说明，不报虚假成功。
9. GitHub 公开源码与安装包；Mac 不上商店，不用 Developer ID 签名/公证，如实说明首次拦截。

## Windows 架构与状态

`workspace/` 是 .NET 8 WPF 外壳，通过 Win32 承载现有 pywebview 工具。隐藏启动握手、统一任务栏图标、关闭保护解决闪窗和多个图标。

公开版本曾发布 v0.3.6；源码包含 v0.3.7 更新机制。是否已有某个公开安装包须检查 Releases，不能把源码版本当作二进制已发布。

更新后台比较 GitHub 版本；仅接受完整且校验通过的 Windows 资产。安装版静默运行安装程序，便携版事务性覆盖发布文件，失败提供恢复保护，不触碰 Agent 数据、不强停工具。原理与验证见 `UPDATES.md`、`UPDATER-QA.md`。

## Mac 移植选择

WPF/Win32 不能移植到 macOS，更不能改 EXE 后缀。保留 Windows，新增 `macos/` 的单个 Cocoa/WebKit 窗口。

`prepare_macos.py` 在构建目录包裹共享页面，不复制出另一套搬家 JS。Python API、分组、弹窗、任务和修改后的 Rust 引擎仍共用。Apple Silicon 和 Intel 在 GitHub 对应真实 Mac runner 编译，自带运行组件形成 APP/DMG。

首版 `0.4.0-macos-preview.1` 与 Windows 下载分开；Windows 更新器不把缺少 Windows 完整资产的 Mac 发布当成更新。Mac 首版是后台提醒、检查更新与下载入口，用户退出后替换应用，尚无自动覆盖更新。

2026-10-12 的首批两架构包在 macOS 15 原生构建，隔离导入、冻结资源、Cocoa 窗口/桥和 DMG 检查通过。首轮发现的空测试账户与加载时序问题、复测链接及后续真机验收边界见 `MACOS-QA.md`；不要重复发布失败或被替代的构建。

2026-10-13 作者反馈检查更新连接失败、Mac 豆包工作没有显示。preview.2 修复 Mac 豆包的 Default 目录识别，并将同一工作区传给导出引擎；刷新同时重新寻找来源。更新 HTTPS 改用系统证书而非打包机器的 Python CA 路径，保留系统代理、严格证书校验和可信仓库过滤，失败显示脱敏分类与下载页入口。新增冻结应用真实 HTTPS 检查，弥补首版未测这一层的缺口；作者 Mac 的具体网络原因仍需新版提示确认。构建结果以 MACOS-QA.md 为准。

2026-10-13 后续需求：Windows 和 Mac 都用“下载并更新”按钮，有新版自动显示，用户点击后下载、校验、等搬运结束再安全替换并重启。Windows 沿用已有更新器，v0.3.8 统一文案；Mac preview.3 新增独立 helper、系统原子交换和失败恢复，四类冻结检查全部通过才发 DMG。preview.1/2 没有自动替换代码，须最后一次手动换成 preview.3；以后不再拖应用。详见 UPDATES.md、MACOS-UPDATES.md 和 MACOS-QA.md；当前发布状态要查 Releases。

## 代码地图

| 位置 | 职责 |
| --- | --- |
| `workspace/` | Windows UI、承载、更新、自检 |
| `dialog-mover/main.py` | 软件、会话、文件夹、任务、打开结果 API |
| `dialog-mover/core/common.py` | 平台路径、URI、只读数据库、系统打开 |
| `dialog-mover/core/sources.py` | 真实列表、过滤、分组、正文可读性 |
| `dialog-mover/core/mover.py` | 引擎、去重、任务、导入验证与续聊命令 |
| `dialog-mover/core/imports.py` | 目标能力、预检、千问登记 |
| `dialog-mover/core/codex_import.py` | ChatGPT 本机结构、备份、项目与模式登记 |
| `dialog-mover/core/chatgpt.py` | 本机/云端合并、排序、缓存 |
| `dialog-mover/ui/` | 共享工具 UI、实际 Logo |
| `macos/entry.py` | Cocoa 单窗口/单实例、更新桥、冻结包/窗口自检 |
| `macos/updates.py` | 系统 HTTPS、可信仓库按架构选版本 |
| `macos/updater.py` | 软件内下载、校验、独立 helper、安全替换与重启 |
| `macos/ui/` | 外层 UI 与侧栏 |
| `macos/AI-First-Tools.spec` | Cocoa、原生引擎、资源、应用信息 |
| `scripts/package_macos.py` | 许可证、打包、自检、Cocoa 检查、DMG/校验值 |
| `txcript/` | 修改后的完整上游，引擎 0.14.4，Rust 最低 1.96 |
| `.github/workflows/macos.yml` | 两架构原生构建，不在 Windows 伪造 APP |

## 安全和真实验证

数据库结构先检查，登记前备份、事务内验证。第三方存储回滚能力不同，不能承诺全部迁移全局原子。源数据库只读，导出临时规范文件再导入，验证后才登记成功。

测试只用临时目录与合成记录，不读取/提交真实认证、Cookie、聊天、完整个人路径、环境全量转储。没有云端认证但有本机任务不应隐藏入口。

构建、窗口可打开、回读、原生软件显示、下一轮对话是不同层次。不要称全部已测试；不自动发付费模型请求。打包工具可能生成 Apple Silicon 必需 ad-hoc 签名，但不是 Developer ID、公证或苹果审核。

新对话先读 `MACOS-HANDOFF.md`，检查 Git 和 CI，按用户现象定位模块。不要重写已验证业务、反复导入、放宽安全检查或关闭系统保护来掩盖问题。
