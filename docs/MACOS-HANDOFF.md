# 在 Mac 的 ChatGPT 中继续开发

## 可直接给新对话的背景

> 我在继续开发 feifeigong/ai-first-tools。先读 AGENTS.md、docs/DEVELOPMENT-CONTEXT.md、docs/MACOS.md 和本文件，再检查 Git、Mac 架构与最近 CI，不重复已完成修改。AI一手工具工作台面向非技术用户，当前自制工具是对话搬家。Windows WPF 保留；Mac 是 Python/pywebview Cocoa/WebKit 单窗口，共用 dialog-mover UI、Python 业务、修改后的 txcript。GitHub 发布 DMG，不上商店，不用 Developer ID/公证。根据我提供的错误排查，保持只复制、搬运中不强退、实际 Logo、真正隐藏侧栏和简单操作。不要读/上传真实认证、Cookie、聊天，先用隔离合成记录。不要把回读称为所有原生显示/续聊通过。

历史背景不是新的操作授权；当前需求、文件和最近验证结果优先。

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
python -m unittest test_chatgpt test_close_safety test_doubao test_macos test_macos_native -v
cd ..
python scripts/package_macos.py --architecture "$(uname -m)"
```

- `test_macos`：路径、中文空格/URI、只读 DB、系统打开、版本选择、UI/Logo 复用。
- `test_macos_native`：真实 Mac 引擎在隔离合成存储中对文件型目标导入/回读，核对编号、路径与源文件不变；拒绝不匹配 DB。
- OpenCode 需额外原生 CLI，这批文件型目标检查不包括它。
- 冻结包 `--self-test` 验证资源与引擎；`--smoke-test` 在空用户目录打开真实 Cocoa 窗口，验证 WebKit/Python 桥、侧栏和 API。
- preview.2 新增冻结包 `--network-test`：在不存在的 Python CA 路径环境中，用系统 Keychain 验证 HTTPS、读取本项目公开 GitHub 发布列表；失败阻止 DMG 发布，不记录代理地址/认证/环境。
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

工作台状态：`~/Library/Application Support/AI一手工具工作台/`；搬家缓存/历史/备份：`~/Library/Application Support/对话搬家/`。不要上传整目录。自定义 CODEX_HOME 可由启动环境提供；Finder 不保证继承终端环境，后续可加明确设置，不全盘扫描。

## 发布维护

- macos/version.json 当前准备版本为 0.4.0-macos-preview.2；公开资产是否发布以 Releases 和 MACOS-QA.md 为准。
- 首批两架构包构建源码为 `2b49c7f`，Mac/Windows CI 均通过；构建链接、SHA-256 和未验收项见 MACOS-QA.md。后续只整理交接文档，不能把文档提交说成重做了安装包。
- 两架构 DMG 名称 `AI-First-Tools-<release>-macos-<architecture>.dmg`，附 SHA-256。
- CI/报告通过才发布下载包；源码提交不等于已发布应用。
- 更新拒绝草稿/旧版本/错误域名/不匹配架构。
- 不加 xattr 解锁脚本，不关闭 Gatekeeper，不宣称苹果审核。
- Windows 与 Mac 的下载和更新能力分开说明。

进展以 MACOS-QA.md 和当前 Actions 为准。Windows 仅验证共享业务/浏览器布局，真实 Mac 应用由 macOS runner 检查；最终第三方列表/续聊由作者实机验收。
