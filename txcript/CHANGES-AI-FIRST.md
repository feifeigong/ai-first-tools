# AI一手本地修改说明

本目录基于 `skillsynchq/txcript` 上游提交 `8cd3b0e63f797b1531a14197f41a0e9eeedec8c6`。

保留上游 Apache-2.0 许可证、作者信息和原有文档。上游 README 描述上游项目；本工作台当前支持范围请看根目录的 `docs/SUPPORT.md`。

本地修改涉及 CLI 结构化列表/导入结果、Windows Cowork 路径、ChatGPT 本机 Work/Codex 原生记录、Antigravity 与 OpenCode 适配、标题和上下文保留、相关回归，以及新增 WorkBuddy、千问办公、豆包工作适配器。豆包本地文件写入不能保证服务器正式会话创建，因此工作台不开放它作为原生搬入目标。

此版本没有把普通云端 ChatGPT/Claude 聊天改成可写目标，没有复制用户登录状态或模型权限。
