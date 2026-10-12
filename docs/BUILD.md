# 开发与构建

普通用户只需下载安装包。以下内容供开发者使用。

## 目录

- `workspace/`：WPF 单窗口工作台。
- `dialog-mover/`：Python / pywebview 对话搬家界面与本机适配。
- `txcript/`：修改后的 Rust 迁移引擎，保留上游许可证与文档。
- `installer/`：NSIS 当前用户安装程序，不要求管理员权限。
- `scripts/`：打包、许可证收集、发布包检查。

## 开发环境

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

```powershell
.\scripts\package.ps1 -Python .\.venv\Scripts\python.exe `
  -MoverPackage .\dialog-mover\dist\对话搬家 `
  -AnalysisToc .\dialog-mover\build\对话搬家\Analysis-00.toc `
  -NsisDirectory C:\BuildTools\nsis-3.12 `
  -WebViewBootstrapper C:\BuildTools\MicrosoftEdgeWebview2Setup.exe
```

生成安装包、免安装 ZIP 与 SHA-256 校验文件，位于 `artifacts/release/`。工作台以自带 .NET 的方式发布，迁移引擎旁也带所需 Visual C++ 运行库；原应用源码和引擎不因打包而改写。

安装器只在当前用户的固定程序目录写入，运行时拒绝更新/卸载，不强制结束搬运。卸载按生成的文件清单逐个删除，不递归清空任意目录，也不删除用户新增文件或 Agent 历史。

发布前须检查源码和包中没有真实账户、记录、日志和私人截图，核对源程序/引擎哈希，执行安装、启动、更新保护、卸载保护和关键回归。没有 Windows 全新虚拟机验收时，不能宣称已覆盖全新系统。

v0.3.5 / v0.3.6 使用相同的既有已测试引擎，SHA-256：`799b80dff7ba44cb05f1a92ed5f64a4969ffefc5ad7b3566600ed88adaaaacd2`。

