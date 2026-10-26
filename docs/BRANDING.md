# AI一手工具箱命名与兼容

产品正式名称为 **AI一手工具箱**，紧凑标题用 **工具箱**，预览应用显示 **AI一手工具箱预览**。公司和现有 Logo 仍用 **AI一手**。窗口、系统应用名、安装/卸载、快捷方式、提醒、搬家说明和当前文档均使用新名称。

下面是既有安装的技术身份，不是旧的对外品牌，不能机械替换或移动：

| 兼容项 | 保留原因 |
| --- | --- |
| Windows `AI一手工具工作台` 程序集与 apphost | 已发布的更新器要求此入口，旧版回滚也依赖它。新发布同时提供内容相同的 `AI一手工具箱.exe` 启动器。 |
| Windows 现有本地应用资料目录、安装目录和注册表键 | 沿用现有记录、资料绑定、续跑开关及卸载登记，不另建空资料区。 |
| Mac 旧 `.app` 物理路径、`AI First Tools` 可执行文件与 `cn.aifirst.tools[.preview]` | 旧客户端从 DMG 查找固定目录，LaunchAgent 与后台身份检查也依赖这些值。 |
| Mac 基础 `CFBundleName` / `CFBundleDisplayName` | 与物理文件名匹配供 Finder 查询；本地化资源向用户显示新产品名。原生检查必须读取系统解析后的显示名。 |
| GitHub 仓库、英文发布资产前缀和压缩包目录 | 旧版下载器的固定协议，保留完整版本、来源、摘要及路径校验。 |
| 已发布包的历史文件名、校验值及归属标记 | 保留可核验的发布历史，不重写旧记录冒充新版本。 |

安装升级只移除确实指向本安装的旧快捷方式；用户改成其他目标的同名链接、非空目录及额外文件保留。快捷方式的新显示名不改变稳定回滚入口。

Mac 的本地化命名依据 [Apple 的 CFBundleDisplayName 说明](https://developer.apple.com/library/archive/documentation/General/Reference/InfoPlistKeyReference/Articles/CoreFoundationKeys.html)。界面仅显示新名称，兼容细节不放进使用流程。
