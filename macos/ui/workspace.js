(() => {
  "use strict";
  const toggle = document.getElementById("workspace-toggle");
  const checker = document.getElementById("workspace-update");
  const notice = document.getElementById("workspace-notice");
  const message = document.getElementById("workspace-message");
  const download = document.getElementById("workspace-download");
  let initialized = false;
  let checking = false;
  let hasUpdate = false;
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
  const show = (text, available = false, label = "下载新版") => {
    message.textContent = text;
    download.hidden = !available;
    download.textContent = label;
    notice.hidden = false;
  };
  document.getElementById("workspace-dismiss").addEventListener("click", () => { notice.hidden = true; });
  window.aiFirstBusyNotice = () => show("正在搬运，请等这一批完成后再退出。不会强制停止或删除原记录。", hasUpdate);
  const check = async (manual = false) => {
    if (checking || !window.pywebview?.api) return;
    checking = true;
    checker.disabled = true;
    checker.textContent = "正在检查…";
    try {
      const result = await window.pywebview.api.check_update();
      if (result.error) { hasUpdate = false; if (manual) show(result.error, result.canOpenDownloads, "打开下载页"); }
      else if (result.available) { hasUpdate = true; show(`有新版本 ${result.version}，下载后拖到“应用程序”替换即可。`, true); }
      else { hasUpdate = false; if (manual) show("已经是当前最新的 Mac 版本。"); }
    } catch { if (manual) show("暂时无法检查更新，您可以继续使用。", hasUpdate); }
    finally { checker.disabled = false; checker.textContent = "检查更新"; checking = false; }
  };
  checker.addEventListener("click", () => check(true));
  download.addEventListener("click", async () => {
    download.disabled = true;
    try { const result = await window.pywebview.api.open_update(); if (result.error) show(result.error, true); }
    finally { download.disabled = false; }
  });
  const start = async () => {
    if (initialized || !window.pywebview?.api) return;
    initialized = true;
    try {
      const info = await window.pywebview.api.workspace_info();
      document.getElementById("workspace-version").textContent = `Mac · v${info.release || info.version}`;
      checker.disabled = false;
      if (info.automaticChecks) setTimeout(() => check(false), 2000);
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
