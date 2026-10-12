# AI一手 · 工具工作台

把好用的 AI 小工具放在一起。打开一个窗口，点一下就能用。

当前内置 **对话搬家**：把支持的 AI 软件中的对话记录复制到另一个软件，原记录保留。

![对话搬家界面](docs/assets/dialog-mover.png)

*界面使用合成示例记录，不包含真实用户对话。*

## 下载安装

**适用于 Windows 10 / 11，64 位电脑。目前为预览版。**

### 推荐：安装版

**[⬇ 下载 Windows 安装包 v0.3.5](https://github.com/feifeigong/ai-first-tools/releases/download/v0.3.5/AI-First-Tools-Setup-0.3.5.exe)**

1. 下载上面的安装包，双击打开。
2. 点击「安装」，等它完成。
3. 以后双击桌面的 **AI一手工具工作台** 图标就能使用。

**不用下载源代码，不用 Git，不用 Python，也不用自己安装 .NET。** 安装到当前用户目录，不要求管理员权限。第一次使用若缺少微软 WebView2，安装程序会联网准备它。

安装包暂未购买代码签名证书，Windows 可能提示「未知发布者」。请核对本仓库、版本与校验文件；不放心请先停止安装，不需要关闭杀毒软件或修改系统安全设置。

### 可选：免安装版

**[⬇ 下载免安装压缩包 v0.3.5](https://github.com/feifeigong/ai-first-tools/releases/download/v0.3.5/AI-First-Tools-Portable-0.3.5-win-x64.zip)**

解压**整个压缩包**，进入文件夹，双击「AI一手工具工作台.exe」。不能只拿走一个 EXE，也不要直接在压缩包里面运行。可以给这个 EXE 创建桌面快捷方式，以后不用再找文件夹。

如果电脑没有 WebView2，优先使用上面的安装版。

## 怎么搬对话

打开工作台 → 点「对话搬家」→ 选择来源软件与记录 → 点「搬到…」→ 选择目标软件及模式 → 选择文件夹 → 确认搬运。

- 自动寻找本机支持的 AI 软件与历史记录；软件需要已安装并产生过记录。
- 项目/文件夹和无目录记录分别展示，文件夹可以收起。
- ChatGPT 的本机 Work / Codex、Claude 的本机 Cowork / Claude Code，分别选择对应模式。
- 只复制对话，不删除原记录；项目文件、附件、登录状态、模型权限和运行环境不会一起搬过去。
- 开始前请备份重要记录，搬完后到目标软件检查标题、正文和文件夹。

## 支持范围

| 类型 | 当前能力 |
| --- | --- |
| Cursor、WorkBuddy、WorkBuddy AI、千问办公 | 支持本机记录搬入/搬出 |
| ChatGPT | 普通云端聊天可读取；**本机 Work / Codex** 可作为目的地 |
| Claude | 普通聊天可读取；**Claude Code / 已初始化的本机 Cowork** 可作为目的地 |
| Antigravity、Cursor CLI、Grok CLI、OpenCode | 本地适配，具体限制见下方说明 |
| 豆包工作、Hermes | 当前界面只支持搬出，不承诺原生搬入 |

**不是每种软件、每个版本都已完成原生界面和继续对话的验收。** “写入后回读通过”不等于附件、工具调用和下一轮对话必定可用。尤其 Antigravity 桌面端的自动重新索引尚未全面验证。

[支持范围与验证边界](docs/SUPPORT.md) · [隐私与数据安全](docs/PRIVACY.md) · [开发与构建](docs/BUILD.md)

## 更新、卸载与反馈

- 更新：关闭工作台后，安装新版本即可。历史记录仍在各 AI 软件自己的目录里。
- 卸载：Windows「设置 → 应用」中找到「AI一手工具工作台」。卸载不删除各 AI 软件的对话，也不主动删除工作台的用户配置。
- 反馈：[提交问题](https://github.com/feifeigong/ai-first-tools/issues)，附版本、Windows 版本、来源和目标软件即可。**不要贴登录令牌、完整聊天或个人路径。**

## 开源与致谢

工作台和对话搬家在 [Apache-2.0](LICENSE) 下开源。本地迁移引擎基于 [skillsynchq/txcript](https://github.com/skillsynchq/txcript)，包含本项目的适配与修复；修改后的引擎源码位于 `txcript/`，上游来源和修改说明见 [NOTICE](NOTICE)。

第三方依赖遵循各自许可证。软件名称和品牌 Logo 归其权利人所有，展示不代表官方合作或授权；代码许可证不授予第三方商标使用权。
