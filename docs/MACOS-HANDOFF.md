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

工作台状态：`~/Library/Application Support/AI一手工具工作台/`；搬家缓存/历史/备份：`~/Library/Application Support/对话搬家/`。不要上传整目录。自定义 CODEX_HOME 可由启动环境提供；Finder 不保证继承终端环境，后续可加明确设置，不全盘扫描。

## 发布维护

- 当前公开 preview.6，构建源码 9703d4335043526fe3ad0ecb00fdba6e31b83ac4，两轮两架构各 74 项单测和资源/窗口/HTTPS/更新四类冻结检查通过，11 个资产独立核对后发布。自动查询失败提示并按 1/5/15/60 分钟退避，限流等一小时；Cocoa 的两套 UI 等原生 loaded 后 ai-first-ready 信号才初始化。49 项本地定向及完整 21 项浏览器回归通过。源码标签取真实构建提交，文档未重做包。preview.1/2 必须最后一次手动替换，preview.3/4 可软件内更新；用户真实公网升级与第三方续聊仍未验收。
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
## 本轮补充：preview.7 长对话分页导入

- 用户现象是 Cursor → 本机 Work 只显示尾部，上翻「重试」无效；不是更新检查问题。
- 旧版原生 `thread/read` 通过不等于分页通过。旧 legacy 导入可复现 `thread/items/list` 返回不支持；见 `dialog-mover/test_codex_native.py` 新增长对话测试。
- 新导入用 paginated 元数据、完整 `item_completed`、稳定轮次/消息 UUID、从零连续 ordinal；保留原协议内容，不手写目标分页数据库，让目标原生恢复线程建立投影。
- 旧版搬过的记录更新后重新搬一次，创建新副本，不修改旧副本或源。新格式成功后恢复去重。
- 新增 `test_codex_history.py` 完整性/格式/旧去重回归；Mac CI 下载 SHA 固定的官方 0.162.1 引擎，三个原生历史测试均禁止模型请求。CI 测试引擎不进入发行包。
- 不把原生引擎分页验证说成用户 Mac 的 ChatGPT 界面手工滚动或实际发送续聊已经完成。发布状态以 GitHub 和下一节 QA 为准。
