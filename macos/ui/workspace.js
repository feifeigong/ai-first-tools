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
  let initializing = false;
  let startTimer = null;
  let startRetryCount = 0;
  let initializationNotice = null;
  let checking = false;
  let hasUpdate = false;
  let installing = false;
  let updating = false;
  let preparingSince = null;
  let handoffSince = null;
  let closingUpdate = false;
  let updateTimer = null;
  const updateRequests = new Set();
  const updateCall = (name) => {
    const request = window.pywebview.api[name]();
    updateRequests.add(request);
    return request.finally(() => updateRequests.delete(request));
  };
  const preparationLabels = {
    mounting: "正在打开安装包（1/8）", checking_current: "正在检查当前应用（2/8）",
    checking_package: "正在检查新版应用（3/8）", copying: "正在复制新版文件（4/8）",
    preparing_helper: "正在准备更新程序（5/8）", verifying: "正在复核更新文件（6/8）",
    fingerprinting: "正在核对应用完整性（7/8）", unmounting: "正在释放安装包（8/8）"
  };
  let automaticChecks = false;
  let checkTimer = null;
  let retryCount = 0;
  let failureNotice = null;
  let announcedVersion = null;
  let lastCheckAt = null;
  let retryAfter = 0;
  const checkInterval = 10 * 60 * 1000;
  const wakeInterval = 2 * 60 * 1000;
  const retryDelays = [60000, 300000, 900000, 3600000];
  const startRetryDelays = [1000, 5000, 30000, 60000];
  // A lost bridge reply must not leave checking/initializing true indefinitely.
  const bridgeRead = (name, timeout) => {
    let timer;
    return Promise.race([
      Promise.resolve().then(() => window.pywebview.api[name]()),
      new Promise((_, reject) => { timer = setTimeout(() => reject(new Error("bridge_timeout")), timeout); })
    ]).finally(() => clearTimeout(timer));
  };
  const scheduleCheck = delay => {
    if (!automaticChecks) return;
    clearTimeout(checkTimer);
    checkTimer = setTimeout(() => check(false), delay);
  };
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
      try { await updateCall("cancel_update"); }
      finally { if (!closingUpdate) dismiss.disabled = false; }
    } else notice.hidden = true;
  });
  window.aiFirstBusyNotice = () => show("正在搬运，请等这一批完成后再退出。不会强制停止或删除原记录。", hasUpdate);
  const check = async (manual = false) => {
    if (checking || updating || !window.pywebview?.api) {
      if (!manual) scheduleCheck(60000);
      return;
    }
    clearTimeout(checkTimer);
    checking = true;
    lastCheckAt = Date.now();
    checker.disabled = true;
    checker.textContent = "正在检查…";
    let failure = null;
    const showFailure = result => {
      failure = result;
      checker.title = result.error;
      if (result.retainedUpdate && hasUpdate) {
        if (manual) show(result.error, true, installing ? "下载并更新" : "打开下载页");
        return;
      }
      hasUpdate = false;
      installing = false;
      announcedVersion = null;
      download.hidden = true;
      if (manual) show(result.error, result.canOpenDownloads, "打开下载页");
      else if (!failureNotice) show(`${result.error} 将自动重试，恢复连接后会主动提示新版本。`);
      if (manual || !failureNotice) failureNotice = message.textContent;
    };
    try {
      const result = await bridgeRead("check_update", 30000);
      if (result.error) showFailure(result);
      else {
        retryCount = 0;
        checker.title = "检查是否有新版本";
        if (failureNotice && message.textContent === failureNotice) notice.hidden = true;
        failureNotice = null;
        if (result.available) {
          hasUpdate = true; installing = result.canInstall === true;
          download.hidden = false;
          download.textContent = installing ? "下载并更新" : "打开下载页";
          if (manual || announcedVersion !== result.version) {
            show(`发现新版本 ${result.version}，${installing ? "点一下即可更新并重新打开。" : "可以打开下载页获取完整安装包。"}`, true, download.textContent);
          }
          announcedVersion = result.version;
        }
        else {
          hasUpdate = false; installing = false; announcedVersion = null; download.hidden = true;
          if (manual) show("已经是当前最新的 Mac 版本。");
          else if (message.textContent.startsWith("发现新版本 ")) notice.hidden = true;
        }
      }
    } catch { showFailure({error: "暂时无法检查更新，您可以继续使用。", canOpenDownloads: true}); }
    finally {
      checker.disabled = false;
      checker.textContent = "检查更新";
      checking = false;
      if (failure) {
        retryCount += 1;
        const delay = failure.errorCode === "rate_limit" ? 3600000 : retryDelays[Math.min(retryCount - 1, retryDelays.length - 1)];
        retryAfter = Date.now() + delay;
        scheduleCheck(delay);
      } else { retryAfter = 0; scheduleCheck(checkInterval); }
    }
  };
  checker.addEventListener("click", () => check(true));
  const finishUpdate = text => {
    updating = false;
    preparingSince = null;
    handoffSince = null;
    clearTimeout(updateTimer);
    checker.disabled = download.disabled = false;
    dismiss.disabled = false;
    progress.hidden = true;
    dismiss.textContent = "×";
    dismiss.setAttribute("aria-label", "关闭提示");
    show(text, hasUpdate, installing ? "下载并更新" : "打开下载页");
  };
  const showHandoff = () => {
    if (handoffSince === null) handoffSince = Date.now();
    const elapsed = Math.max(0, Math.floor((Date.now() - handoffSince) / 1000));
    message.textContent = `正在启动更新程序 · 已用时 ${elapsed} 秒`;
    dismiss.disabled = true;
  };
  window.aiFirstFinishUpdate = async () => {
    closingUpdate = true;
    clearTimeout(updateTimer);
    message.textContent = "正在更新并重新打开，请稍等…";
    dismiss.disabled = true;
    await Promise.allSettled([...updateRequests]);
    return {ready: true, pendingUpdates: updateRequests.size};
  };
  window.aiFirstResumeUpdate = () => {
    closingUpdate = false;
    finishUpdate("更新重启交接未完成，当前版本未改动。可以重试或打开下载页。");
  };
  const pollUpdate = async () => {
    if (!updating || closingUpdate) return;
    try {
      const state = await updateCall("update_status");
      if (closingUpdate) return;
      progress.hidden = false;
      if (state.phase === "downloading") {
        progress.value = Math.min(100, Math.max(0, state.progress || 0));
        message.textContent = `正在下载 ${Math.floor(progress.value)}% · 下载时可以继续使用`;
      } else if (state.phase === "preparing") {
        if (preparingSince === null) preparingSince = Date.now();
        progress.removeAttribute("value");
        const elapsed = Math.max(0, Math.floor((Date.now() - preparingSince) / 1000));
        message.textContent = state.cancelRequested ? "正在取消更新，当前版本保持不变…" :
          `${preparationLabels[state.step] || "正在准备更新"} · 已用时 ${elapsed} 秒`;
        dismiss.disabled = state.cancelRequested === true;
      } else if (state.phase === "ready") {
        progress.value = 100;
        showHandoff();
        const result = await updateCall("apply_update");
        if (closingUpdate) return;
        if (result.error) { finishUpdate(result.error); return; }
        if (result.waiting) { message.textContent = "下载完成，等当前搬运结束后自动更新。"; dismiss.disabled = false; handoffSince = null; }
        else if (!result.starting) { message.textContent = "正在更新并重新打开，请稍等…"; dismiss.disabled = true; return; }
      } else if (state.phase === "starting") {
        showHandoff();
      } else if (state.phase === "restarting") {
        message.textContent = "正在更新并重新打开，请稍等…";
        dismiss.disabled = true;
        return;
      } else if (state.phase === "error") { finishUpdate(state.error); return; }
      updateTimer = setTimeout(pollUpdate, 600);
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
      const result = await updateCall("start_update");
      if (result.error) { show(result.error, true); return; }
      updating = true;
      closingUpdate = false;
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
    if (window.pywebview?.platform === "cocoa" && !window.__AI_FIRST_BRIDGE_READY__) return;
    if (initialized || initializing || !window.pywebview?.api) return;
    clearTimeout(startTimer);
    initializing = true;
    try {
      const info = await bridgeRead("workspace_info", 10000);
      initialized = true;
      startRetryCount = 0;
      if (initializationNotice && message.textContent === initializationNotice) notice.hidden = true;
      initializationNotice = null;
      document.getElementById("workspace-version").textContent = info.developmentPreview ? 'Mac · 本地预览' : `Mac · v${info.release || info.version}`;
      checker.disabled = false;
      checker.hidden = Boolean(info.developmentPreview);
      if (info.automaticChecks) {
        automaticChecks = true;
        if (info.updateMessage) show(info.updateMessage);
        scheduleCheck(2000);
      }
      if (info.smokeAudit) {
        const agents = await window.pywebview.api.agents();
        toggle.click();
        const hidden = getComputedStyle(document.getElementById("workspace-nav")).display === "none";
        const expanded = toggle.getAttribute("aria-expanded") === "false";
        toggle.click();
        window.__AI_FIRST_SMOKE__ = { passed: hidden && expanded && agents.ready && agents.agents.length === 0,
          checks: { sidebarHidden: hidden, sidebarState: expanded, nativeEngineReady: agents.ready, isolatedRecords: agents.agents.length === 0, bridge: true },
          scope: "Cocoa window, WebKit UI and Python bridge; synthetic empty user profile" };
      }
    } catch {
      initialized = false;
      if (!initializationNotice) {
        initializationNotice = "工作台连接暂未就绪，正在自动重试。您无需点击检查更新。";
        show(initializationNotice);
      }
      const delay = startRetryDelays[Math.min(startRetryCount, startRetryDelays.length - 1)];
      startRetryCount += 1;
      startTimer = setTimeout(start, delay);
    } finally { initializing = false; }
  };
  const wake = () => {
    if (!initialized) { start(); return; }
    if (!automaticChecks || checking || updating || document.visibilityState === "hidden" || lastCheckAt === null) return;
    if (Date.now() >= retryAfter && Date.now() - lastCheckAt >= wakeInterval) scheduleCheck(250);
  };
  window.addEventListener("pywebviewready", start);
  window.addEventListener("ai-first-ready", start);
  window.addEventListener("focus", wake);
  window.addEventListener("online", wake);
  document.addEventListener("visibilitychange", wake);
  startTimer = setTimeout(start, 500);
})();
