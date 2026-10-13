(() => {
  "use strict";
  const toggle = document.getElementById("workspace-toggle");
  const checker = document.getElementById("workspace-update");
  const notice = document.getElementById("workspace-notice");
  const message = document.getElementById("workspace-message");
  const download = document.getElementById("workspace-download");
  const progress = document.getElementById("workspace-progress");
  const dismiss = document.getElementById("workspace-dismiss");
  let initialized = false;
  let checking = false;
  let hasUpdate = false;
  let installing = false;
  let updating = false;
  const drawToggle = () => {
    const collapsed = document.body.classList.contains("workspace-collapsed");
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.setAttribute("aria-label", collapsed ? "显示工具栏" : "隐藏工具栏");
    toggle.title = collapsed ? "显示工具栏" : "隐藏工具栏";
    toggle.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16"/>${collapsed ? '<path d="m5 10 2 2-2 2"/>' : '<path d="M4 5h4v14H4z" fill="currentColor" opacity=".18" stroke="none"/>'}</svg>`;
  };
  try { document.body.classList.toggle("workspace-collapsed", localStorage.getItem("ai-first-sidebar-collapsed") === "true"); } catch {}
  drawToggle();
  toggle.addEventListener("click", () => {
    document.body.classList.toggle("workspace-collapsed");
    drawToggle();
    try { localStorage.setItem("ai-first-sidebar-collapsed", String(document.body.classList.contains("workspace-collapsed"))); } catch {}
  });
  const show = (text, available = false, label = "下载并更新") => {
    message.textContent = text;
    download.hidden = !available;
    download.textContent = label;
    notice.hidden = false;
  };
  dismiss.addEventListener("click", async () => {
    if (updating) {
      dismiss.disabled = true;
      try { await window.pywebview.api.cancel_update(); }
      finally { dismiss.disabled = false; }
    } else notice.hidden = true;
  });
  window.aiFirstBusyNotice = () => show("正在搬运，请等这一批完成后再退出。不会强制停止或删除原记录。", hasUpdate);
  const check = async (manual = false) => {
    if (checking || updating || !window.pywebview?.api) return;
    checking = true;
    checker.disabled = true;
    checker.textContent = "正在检查…";
    try {
      const result = await window.pywebview.api.check_update();
      if (result.error) { hasUpdate = false; installing = false; download.hidden = true; if (manual) show(result.error, result.canOpenDownloads, "打开下载页"); }
      else if (result.available) {
        hasUpdate = true; installing = result.canInstall === true;
        show(`发现新版本 ${result.version}，${installing ? "点一下即可更新并重新打开。" : "可以打开下载页获取完整安装包。"}`, true, installing ? "下载并更新" : "打开下载页");
      }
      else { hasUpdate = false; installing = false; download.hidden = true; if (manual) show("已经是当前最新的 Mac 版本。"); }
    } catch { if (manual) show("暂时无法检查更新，您可以继续使用。", hasUpdate); }
    finally { checker.disabled = false; checker.textContent = "检查更新"; checking = false; }
  };
  checker.addEventListener("click", () => check(true));
  const finishUpdate = text => {
    updating = false;
    checker.disabled = download.disabled = false;
    progress.hidden = true;
    dismiss.textContent = "×";
    dismiss.setAttribute("aria-label", "关闭提示");
    show(text, hasUpdate, installing ? "下载并更新" : "打开下载页");
  };
  const pollUpdate = async () => {
    if (!updating) return;
    try {
      const state = await window.pywebview.api.update_status();
      progress.hidden = false;
      if (state.phase === "downloading") {
        progress.value = Math.min(100, Math.max(0, state.progress || 0));
        message.textContent = `正在下载 ${Math.floor(progress.value)}% · 下载时可以继续使用`;
      } else if (state.phase === "preparing") {
        progress.removeAttribute("value");
        message.textContent = "正在校验更新包，当前版本保持不变…";
      } else if (state.phase === "ready") {
        progress.value = 100;
        const result = await window.pywebview.api.apply_update();
        if (result.error) { finishUpdate(result.error); return; }
        if (result.waiting) message.textContent = "下载完成，等当前搬运结束后自动更新。";
        else { message.textContent = "正在更新并重新打开，请稍等…"; dismiss.disabled = true; return; }
      } else if (state.phase === "error") { finishUpdate(state.error); return; }
      setTimeout(pollUpdate, 600);
    } catch { finishUpdate("更新连接暂时中断，当前版本和备份仍保留。请重新打开软件后查看结果。"); }
  };
  download.addEventListener("click", async () => {
    if (updating) return;
    download.disabled = true;
    try {
      if (!installing) {
        const result = await window.pywebview.api.open_update();
        if (result.error) show(result.error, true, "打开下载页");
        return;
      }
      const result = await window.pywebview.api.start_update();
      if (result.error) { show(result.error, true); return; }
      updating = true;
      checker.disabled = true;
      download.textContent = "正在更新…";
      dismiss.textContent = "取消";
      dismiss.setAttribute("aria-label", "取消更新");
      notice.hidden = false;
      pollUpdate();
    } catch { show("暂时无法启动更新，当前版本可以继续使用。", true); }
    finally { if (!updating) download.disabled = false; }
  });
  const start = async () => {
    if (initialized || !window.pywebview?.api) return;
    initialized = true;
    try {
      const info = await window.pywebview.api.workspace_info();
      document.getElementById("workspace-version").textContent = `Mac · v${info.release || info.version}`;
      checker.disabled = false;
      if (info.automaticChecks) {
        if (info.updateMessage) show(info.updateMessage);
        setTimeout(() => check(false), 2000);
        setInterval(() => check(false), 6 * 60 * 60 * 1000);
      }
      else {
        const agents = await window.pywebview.api.agents();
        toggle.click();
        const hidden = getComputedStyle(document.getElementById("workspace-nav")).display === "none";
        const expanded = toggle.getAttribute("aria-expanded") === "false";
        toggle.click();
        window.__AI_FIRST_SMOKE__ = { passed: hidden && expanded && agents.ready && agents.agents.length === 0,
          checks: { sidebarHidden: hidden, sidebarState: expanded, nativeEngineReady: agents.ready, isolatedRecords: agents.agents.length === 0, bridge: true },
          scope: "Cocoa window, WebKit UI and Python bridge; synthetic empty user profile" };
      }
    } catch { show("工作台连接失败，请重新打开。不会用演示数据替代您的记录。"); }
  };
  window.addEventListener("pywebviewready", start);
  setTimeout(start, 500);
})();
