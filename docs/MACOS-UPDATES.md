# Mac 一键下载更新

## 普通用户

preview.8 的提醒策略为：本机组件就绪后约两秒自动检查，持续运行每十分钟补查；返回窗口、页面重新可见或网络恢复时补查，至少间隔两分钟且遵守失败退避，防止频繁切换造成限流。初始化失败会自动恢复，不会因此永远停止检查。有新版时，顶部出现「下载并更新」，点一次即可；下载进度、取消和等待搬运均在原窗口中显示。下载完成且没有搬运时自动安全关闭，替换并重启，不要求手动打开 DMG 或重复安装。

当前公开版为 preview.8，包含自动提醒与长对话分页导入修复。preview.1/2 没有一键覆盖代码，需最后一次手动升级到 preview.8；preview.3 及之后可以直接在软件内升级，旧版没有自动提醒时先点一次「检查更新」。GitHub 提交不能直接改变旧程序内部的调度。这里只改程序；Agent 对话、登录、工作台设置不在替换范围。旧的导入副本不会自动改写，需要从来源重新搬一次为新副本。

## 安全链路

1. 固定仓库公开 Release，匹配更新版本和当前芯片，只接受完整 DMG 和 SHA256SUMS.txt 的精确 URL、大小、SHA-256 digest。
2. 系统证书校验，下载跳转仅允许 HTTPS GitHub 项目资产及指定 GitHub CDN，不把认证或环境写入包/日志。校验文件与包的哈希再比对，限大小、时间，取消/断流不保留半包。
3. DMG 只读挂载，不在 Finder 弹出；在当前 APP 同一父目录准备私有更新目录。校验 bundle ID、版本、架构、所有符号链接边界、ad-hoc 资源封印，记录应用内容指纹。更新前再次检查指纹，拒绝期间变化。
4. 独立的冻结 helper 副本先确认就绪，旧窗口才关闭；等待原进程自然退出，不强杀。新 APP 在交换前运行资源/原生引擎自检。
5. 使用系统原子交换，把整套 APP 一次性换到原位置，没有“旧目录已删而新目录还没放上”的空档。卷不支持交换则拒绝，不退化为先删旧版；交换/启动失败尝试换回旧版，备份和失败包保留。
6. 以独立的新进程重新打开 APP，不依赖 LaunchServices 对多个同标识应用副本的选择，避免复用旧冻结库；检测立即退出并显示结果。进程存活不等于每台用户 Mac 的 Cocoa 或系统安全提示均已通过；CI 的重启检查在隔离 APP 副本中执行，没有访问用户的实际安装目录。

源文件：macos/updater.py（下载、校验、原子交换和 helper）、macos/entry.py（搬运/退出保护、状态桥）、macos/ui/workspace.js（按钮、进度、等待与取消）。

实现遵循 [PyInstaller 独立重启进程约定](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#using-sys-executable-to-spawn-subprocesses-that-outlive-the-application-process-implementing-application-restart)，设置子进程 PYINSTALLER_RESET_ENVIRONMENT，不修改全局环境。原子交换采用 [Apple 的卷交换能力](https://developer.apple.com/documentation/foundation/urlresourcekey/volumesupportsswaprenamingkey) 与 [公开系统声明](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/stdio.h)。

## preview.4 启动稳定性修复

追加原生更新审计发现页面偶发不加载，虽然 localhost 页面可读取，WebKit 桥仍未开始注入。保持系统 HOME 的审计修订还不足以消除 Intel 复测失败。检查所锁定 pywebview 6.2.1 的 Cocoa 实现，发现 private_mode 会在窗口启动时异步清理共享 WebKit 数据存储；由此推测存在清理与新页面加载竞争，不把推测当成已取得完整系统错误诊断。

preview.4 用 private_mode=False 启动，避免这条异步清理路径，同时明确 DEFAULT_HTTP_PORT=None 保持随机 localhost 端口，不改成固定端口。工作台自己的 WebKit 页面缓存可能保留，不读取其他 Agent 的 Cookie/认证；HTTPS 和更新来源检查不变。审计的业务 home() 与回执单独隔离，系统 HOME 保持原值。这两项都有回归测试；同源码两次完整构建的两架构资源、Cocoa、网络及更新审计全部通过，见 MACOS-QA.md。相关参数见 [pywebview 官方 API](https://pywebview.flowrl.com/api/)。

## 限制与测试

preview.8 修复已复现的提醒缺口：旧策略一次成功后等六小时，不响应返回窗口/网络恢复；工作台信息首次获取失败会把初始化永久标为完成。新策略增加周期和返回补查、可恢复初始化，并保留已经严格验证的更新包：后续临时网络错误不撤掉下载按钮，非法元数据仍清空包。关闭某个版本的提示条不影响顶部按钮，也不在每次补查时反复弹同一条。冻结 Cocoa 检查现在必须证明真实 Python 桥的自动查询产生可见按钮，且没有自行下载；查询使用明确的合成响应、不访问真实聊天。发布情况与未验收边界见 MACOS-QA.md。

preview.6 已修复自动查询失败静默：普通错误在 1/5/15/60 分钟后自动重试，持续错误每小时一次；限流直接延后一小时。成功后恢复六小时检查。手动成功替换待重试任务，下载/更新中不并行查新版本；关闭错误提示不停止后台重试，也不每次重复提示。Cocoa 的工具和工作台初始化等待原生 loaded 后的 ai-first-ready 信号，避免在 Python 就绪前请求 API；Windows 路径不等待此信号。preview.5 因追加 Intel 窗口检查失败未公开；preview.6 两轮两架构均通过，独立核对后发布，证据见 MACOS-QA.md。已安装旧版的代码不会随仓库提交改变。

- 没有 Developer ID/公证，不关闭 Gatekeeper、不清除隔离属性、不自动提权；受管理机器或系统安全拦截仍可能需确认。安装权限不足时保持旧程序，不绕过限制。
- HTTPS/hash/固定发布者提供传输完整性与固定来源约束，不是苹果审核，也不能防止发布者账号被攻破。
- 旧版备份和失败任务目录暂不自动删除，以保留恢复机会；保存在应用旁的私有隐藏目录，不含对话/认证。后续如加入清理，必须只清理完成且无人运行的受控任务。
- 单测覆盖错误地址、缺少校验资产、半包、版本/架构、指纹变化、备份、交换失败恢复、启动失败恢复、迁移中等待与重启时拒绝新迁移；浏览器覆盖自动出现按钮、一次点击、进度、等待和取消。
- 冻结 APP 的 --update-test 在临时目录复制 APP、构造隔离旧版本元数据，验证真实 helper 进程、原子交换和新 APP 的 Cocoa/WebKit/Python 桥重启。这不是作者真实机器上从已发布旧版手点升级的验收。
- 审计进程的业务目录与回执单独隔离，不改系统 HOME，不读取真实 Agent 存储。测试模式修订与实际发布包的构建提交分别记录，不能把后续测试包替换为同版本公开资产。
- 成功构建/测试才发布；报告与仍未验收项见 MACOS-QA.md。
