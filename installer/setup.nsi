Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "WinVer.nsh"
!include "x64.nsh"

!define APP "AI一手工具工作台"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\AIFirstTools"
!define WEBVIEW_KEY "Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

Name "${APP}"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\AI First Tools"
RequestExecutionLevel user
SetCompressor /SOLID lzma
ShowInstDetails nevershow
ShowUninstDetails nevershow
Icon "${ICON}"
UninstallIcon "${ICON}"
VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=2052 "ProductName" "${APP}"
VIAddVersionKey /LANG=2052 "FileDescription" "AI一手工具工作台安装程序"
VIAddVersionKey /LANG=2052 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=2052 "LegalCopyright" "Apache-2.0; third-party components retain their licenses"

!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "欢迎使用 AI一手工具工作台"
!define MUI_WELCOMEPAGE_TEXT "把好用的 AI 小工具放在一起。$\r$\n$\r$\n点击安装，完成后从桌面打开即可。$\r$\n不需要自己安装 Python 或 .NET。$\r$\n$\r$\n如果缺少微软 WebView2，会联网准备。$\r$\n软件不会删除原来的 AI 对话记录。"
!define MUI_FINISHPAGE_TITLE "安装完成，可以开始用了"
!define MUI_FINISHPAGE_TEXT "以后双击桌面的「AI一手工具工作台」即可打开。"
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP}.exe"
!define MUI_FINISHPAGE_RUN_TEXT "现在打开 AI一手工具工作台"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

!macro CheckRunning
  System::Call 'kernel32::OpenMutexW(i 0x100000, i 0, w "Local\AI_FIRST_TOOLS_RUNNING") p.r0'
  ${If} $0 != 0
    System::Call 'kernel32::CloseHandle(p r0)'
    MessageBox MB_OK|MB_ICONINFORMATION "请先关闭 AI一手工具工作台，再重新运行。正在搬运时，请等任务完成后再关闭。" /SD IDOK
    SetErrorLevel 1603
    Abort
  ${EndIf}
!macroend

Function .onInit
  SetShellVarContext current
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_OK "需要 Windows 10 或更新版本。" /SD IDOK
    SetErrorLevel 1633
    Abort
  ${EndIf}
  ${IfNot} ${RunningX64}
    MessageBox MB_OK "这个安装包需要 64 位 Windows。" /SD IDOK
    SetErrorLevel 1633
    Abort
  ${EndIf}
  StrCpy $INSTDIR "$LOCALAPPDATA\Programs\AI First Tools"
  !insertmacro CheckRunning
FunctionEnd

Function WebViewExists
  StrCpy $1 0
  ReadRegStr $0 HKCU "${WEBVIEW_KEY}" "pv"
  ${If} $0 != ""
  ${AndIf} $0 != "0.0.0.0"
    StrCpy $1 1
    Return
  ${EndIf}
  SetRegView 32
  ReadRegStr $0 HKLM "${WEBVIEW_KEY}" "pv"
  ${If} $0 != ""
  ${AndIf} $0 != "0.0.0.0"
    StrCpy $1 1
  ${EndIf}
  SetRegView 64
  ReadRegStr $0 HKLM "${WEBVIEW_KEY}" "pv"
  ${If} $0 != ""
  ${AndIf} $0 != "0.0.0.0"
    StrCpy $1 1
  ${EndIf}
  SetRegView 32
FunctionEnd

Section "安装"
  !insertmacro CheckRunning
  Call WebViewExists
  ${If} $1 == 0
    InitPluginsDir
    SetOutPath "$PLUGINSDIR"
    File /oname=MicrosoftEdgeWebview2Setup.exe "${WEBVIEW_BOOTSTRAPPER}"
    DetailPrint "正在准备微软 WebView2，请保持网络连接…"
    ExecWait '"$PLUGINSDIR\MicrosoftEdgeWebview2Setup.exe" /silent /install' $2
    Call WebViewExists
    ${If} $1 == 0
      MessageBox MB_OK|MB_ICONEXCLAMATION "微软 WebView2 尚未准备好（结果：$2）。请检查网络，然后重新运行安装包。" /SD IDOK
      SetErrorLevel 1603
      Abort
    ${EndIf}
  ${EndIf}
  IfFileExists "$INSTDIR\tools\auto-resume\AI一手续跑后台.exe" 0 ResumePrepared
    nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\assets\auto-resume-bundled.ps1" -Action prepare-update'
    Pop $2
    Pop $3
    ${If} $2 != 0
      MessageBox MB_OK|MB_ICONEXCLAMATION "后台续跑暂未停止，尚未替换程序文件。请在工作台关闭自动续跑后重试。" /SD IDOK
      SetErrorLevel 1603
      Abort
    ${EndIf}
  ResumePrepared:
  SetOutPath "$INSTDIR"
  ClearErrors
  File /r "${PACKAGE}\*"
  ${If} ${Errors}
    MessageBox MB_OK|MB_ICONEXCLAMATION "程序文件没有全部写入。请检查磁盘空间和文件权限，再重新安装。" /SD IDOK
    SetErrorLevel 1603
    Abort
  ${EndIf}
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateShortCut "$DESKTOP\${APP}.lnk" "$INSTDIR\${APP}.exe" "" "$INSTDIR\${APP}.exe" 0
  CreateDirectory "$SMPROGRAMS\${APP}"
  CreateShortCut "$SMPROGRAMS\${APP}\${APP}.lnk" "$INSTDIR\${APP}.exe" "" "$INSTDIR\${APP}.exe" 0
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "${APP}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "Publisher" "AI一手"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\${APP}.exe,0"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "${UNINSTALL_KEY}" "QuietUninstallString" '$\"$INSTDIR\Uninstall.exe$\" /S'
  WriteRegStr HKCU "${UNINSTALL_KEY}" "URLInfoAbout" "https://github.com/feifeigong/ai-first-tools"
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\assets\auto-resume-bundled.ps1" -Action finish-update'
  Pop $2
  Pop $3
  ${If} $2 != 0
    MessageBox MB_OK|MB_ICONINFORMATION "工作台已安装，后台续跑暂未恢复。打开工作台后，在自动续跑页面重新开启即可。" /SD IDOK
  ${EndIf}
SectionEnd

Function un.onInit
  SetShellVarContext current
  GetFullPathName $0 "$LOCALAPPDATA\Programs\AI First Tools"
  GetFullPathName $1 "$INSTDIR"
  ${If} $0 != $1
    MessageBox MB_OK|MB_ICONEXCLAMATION "安装位置不匹配，为保护文件已停止卸载。" /SD IDOK
    SetErrorLevel 1603
    Abort
  ${EndIf}
  IfFileExists "$INSTDIR\${APP}.exe" +4 0
    MessageBox MB_OK|MB_ICONEXCLAMATION "找不到工作台程序，为保护文件已停止卸载。" /SD IDOK
    SetErrorLevel 1603
    Abort
  !insertmacro CheckRunning
FunctionEnd

Section "Uninstall"
  !insertmacro CheckRunning
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\assets\auto-resume-bundled.ps1" -Action uninstall'
  Pop $2
  Pop $3
  ${If} $2 != 0
    MessageBox MB_OK|MB_ICONEXCLAMATION "后台续跑暂未停止，尚未删除工作台。请关闭自动续跑后重试。" /SD IDOK
    SetErrorLevel 1603
    Abort
  ${EndIf}
  !include "${UNINSTALL_MANIFEST}"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  Delete "$DESKTOP\${APP}.lnk"
  Delete "$SMPROGRAMS\${APP}\${APP}.lnk"
  RMDir "$SMPROGRAMS\${APP}"
  DeleteRegKey HKCU "${UNINSTALL_KEY}"
SectionEnd
