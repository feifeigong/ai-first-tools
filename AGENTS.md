# AI一手工具箱开发约定

先读 docs/DEVELOPMENT-CONTEXT.md；Mac 再读 docs/MACOS-HANDOFF.md、docs/MACOS-QA.md。当前文件、Git 和 CI 优先。

- 自制工具箱，不是插件市场。简单中文，不添加内部/外部进程管理 UI。
- Windows WPF 和 Mac Cocoa 入口分开，搬家业务/工具 UI 共用。
- 用既有 AI一手/Agent Logo，搬家外层内层一致；侧栏真隐藏、键盘焦点可见、鼠标无外框。
- 只复制，源只读，结构先检查，搬运中不强退，不发模型请求测试。
- 不读/上传/提交真实认证、Cookie、聊天、DB、环境转储、个人路径；用隔离合成数据。
- 不放宽格式检查，不把回读说成全部原生显示/续聊通过。
- Mac 不用 Developer ID/公证、不上商店、不提供关闭 Gatekeeper 或批量解锁脚本。
- 更新交接/QA；只发布成功且报告通过的运行包。
