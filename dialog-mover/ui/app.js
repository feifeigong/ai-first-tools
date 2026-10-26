(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);

  const LOGOS = {
    cursor_desktop: "cursor", cursor_cli: "cursor", workbuddy: "workbuddy", workbuddy_ai: "workbuddy-ai",
    qwen_work: "qwen", doubao_work: "doubao", antigravity: "antigravity", antigravity_cli: "antigravity",
    codex: "chatgpt", codex_cli: "chatgpt", chatgpt: "chatgpt", chatgpt_work: "chatgpt", claude_code: "claude", claude: "claude",
    claude_desktop: "claude", cowork: "claude", grok: "grok", grokbot: "grok-bot", hermes: "hermes", opencode: "opencode",
    codebuddy: "codebuddy", kimi: "kimi", deepseek: "deepseek", perplexity: "perplexity",
    copilot_desktop: "copilot",
  };
  const SOFTWARE_ICON = '<svg viewBox="0 0 24 24" width="21" height="21" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="15" rx="3"/><path d="M3 9h18M7 6.5h.01M10 6.5h.01"/></svg>';

  function agentLogo(id, name) {
    const asset = LOGOS[id];
    return `<span class="agent-logo ${asset === "chatgpt" ? "agent-logo-chatgpt" : ""}" data-agent-logo="${esc(id)}" title="${esc(name)}">${asset ? `<img src="assets/agents/${asset}.png" alt="${esc(name)} 图标" draggable="false">` : SOFTWARE_ICON}</span>`;
  }

  document.addEventListener("error", (event) => {
    const image = event.target;
    if (!(image instanceof HTMLImageElement) || !image.parentElement?.matches(".agent-logo")) return;
    const container = image.parentElement;
    container.classList.remove("agent-logo-chatgpt");
    container.classList.add("agent-logo-missing");
    container.innerHTML = SOFTWARE_ICON;
    container.title += "：暂未找到原版图标";
  }, true);
  const KIND = { task: "任务", space: "空间", project: "项目", recent: "最近", folder: "文件夹", none: "没有目录" };
  const ICON = {
    folder: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/></svg>',
    task: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/></svg>',
    recent: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    chevron: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>',
    foldIn: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 4l5 5 5-5"/><path d="M7 20l5-5 5 5"/></svg>',
    foldOut: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 9l5-5 5 5"/><path d="M7 15l5 5 5-5"/></svg>',
    tick: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    dash: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round"><path d="M6 12h12"/></svg>',
  };
  const GROUP_ICON = { task: ICON.task, recent: ICON.recent };

  const state = {
    unsupported: [],
    agents: [],
    targets: [],
    smartTargets: [],
    memoryRecords: [],
    current: null,
    cache: {},
    selected: new Set(),
    query: "",
    kind: "all",
    sheet: null,
    folded: {},
    searchFolded: new Set(),
  };

  /* ------------------------------------------------------------ api */
  const real = () => window.pywebview && window.pywebview.api;
  const preview = new URL(window.location.href).searchParams.get("demo") === "1";
  const mock = {
    async agents() {
      return {
        ready: true,
        agents: [
          { id: "cursor_desktop", name: "Cursor", sub: "代码编辑器里的对话", color: "#1f2933", canTarget: true },
          { id: "workbuddy", name: "WorkBuddy", sub: "国内版", color: "#e8590c", canTarget: true },
          { id: "workbuddy_ai", name: "WorkBuddy AI", sub: "海外版", color: "#0c8599", canTarget: true },
          { id: "qwen_work", name: "千问办公", sub: "通义千问", color: "#6741d9", canTarget: true },
          { id: "doubao_work", name: "豆包工作", sub: "字节跳动", color: "#1971c2", canTarget: false },
          { id: "antigravity", name: "Antigravity", sub: "Google", color: "#2f9e44", canTarget: true },
          { id: "chatgpt", name: "ChatGPT", sub: "聊天、工作、桌面 Codex", color: "#0b8f6f", canTarget: false },
          { id: "codex_cli", name: "Codex CLI", sub: "命令行记录", color: "#0b8f6f", canTarget: false, sourceOnly: true },
        ],
      };
    },
    async sessions(id) {
      const s = (n, t, w, f, m = true, note = "") => ({ id: `${id}-${n}`, title: t, when: w, ts: n, folder: f, movable: m, note, kind: id === "chatgpt" ? (n % 2 ? "chat" : "work") : "" });
      const groups = [
        { title: "AI-First-Hand", kind: "folder", path: "C:\\Users\\me\\Documents\\cowork\\AI-First-Hand", sessions: [
          s(9, "Wechat styled HTML file", "23 小时前", "x"), s(8, "同步 GitHub 写作工作流", "20 天前", "x"),
          s(7, "WeChat article covers", "26 天前", "x"), s(6, "Codex multi-agent research report", "2026-09-08", "x"),
          s(20, "Article title and cover design", "27 天前", "x"), s(21, "Model identification inquiry", "28 天前", "x"),
          s(22, "DeepSeek Harness tutorial", "30 天前", "x"), s(23, "Codex context tutorial", "31 天前", "x"), s(24, "Opus writing with AI", "33 天前", "x") ] },
        { title: "vibcoding", kind: "folder", path: "D:\\vibcoding", sessions: [
          s(5, "ChatGPT conversation extraction", "10 分钟前", "y"), s(4, "Agent对话共享工具", "6 天前", "y") ] },
        { title: "没有目录", kind: "none", path: "", sessions: [
          s(3, "Codex WeChat article search", "28 天前", "", true), s(2, "云端对话示例", "30 天前", "", false, "这条对话只保存在云端，不能搬运") ] },
      ];
      return { groups, total: 8, movable: 7 };
    },
    async folders() {
      return [
        { path: "C:\\Users\\me\\Documents\\cowork\\AI-First-Hand", name: "AI-First-Hand" },
        { path: "D:\\vibcoding", name: "vibcoding" },
        { path: "D:\\Projects\\demo-project", name: "demo-project" },
      ];
    },
    async pick_folder() { return "D:\\新建的文件夹"; },
    async open_import_folder() { return { error: "这是界面预览，没有实际导入文件。" }; },
    async open_in_app() { return { error: "这是界面预览，没有实际导入文件。" }; },
    _n: 0,
    async start_move(source, ids) { mock._n = 0; mock._total = ids.length; mock._ids = ids; return { ok: true, total: ids.length }; },
    async move_status() {
      mock._n = Math.min(mock._total, mock._n + 1);
      const items = mock._ids.map((id, i) => ({ id, title: "示例对话 " + (i + 1), state: i < mock._n ? "ok" : "running", message: "已搬好" }));
      return { finished: mock._n >= mock._total, total: mock._total, done: mock._n, ok: mock._n, skipped: 0, failed: 0, items };
    },
  };
  const call = async (name, ...args) => {
    const api = real();
    if (api && api[name]) return api[name](...args);
    return mock[name](...args);
  };

  /* ---------------------------------------------------------- toast */
  function toast(text) {
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = text;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 2600);
  }

  /* ----------------------------------------------------------- rail */
  const label = (agent) => {
    const twins = state.agents.filter((item) => item.name === agent.name).length > 1;
    return twins ? `${agent.name} ${agent.sub}` : agent.name;
  };

  function renderRail() {
    const main = state.agents
      .map((agent) => {
        const data = state.cache[agent.id];
        const count = data && !data.error ? data.total : "";
        return `<button class="agent ${state.current === agent.id ? "active" : ""}" data-agent="${agent.id}">
          ${agentLogo(agent.id, agent.name)}
          <span class="agent-text"><div class="agent-name">${esc(agent.name)}</div><div class="agent-sub">${esc(agent.sub) || "&nbsp;"}</div></span>
          <span class="agent-count">${count}</span>
        </button>`;
      })
      .join("");
    const extra = state.unsupported.length
      ? `<div class="rail-label rail-label-2">还发现这些</div>` +
        state.unsupported
          .map(
            (item) => `<button class="agent dim ${state.current === "x:" + item.id ? "active" : ""}" data-extra="${esc(item.id)}">
              ${agentLogo(item.id, item.name)}
              <span class="agent-text"><div class="agent-name">${esc(item.name)}</div><div class="agent-sub">${esc(item.reason === "empty" ? "暂无对话" : "暂时读不了")}</div></span>
            </button>`
          )
          .join("")
      : "";
    $("#agents").innerHTML = main + extra;
  }

  function showExtra(id) {
    const item = state.unsupported.find((entry) => entry.id === id);
    if (!item) return;
    state.current = "x:" + id;
    state.selected = new Set();
    updateBar();
    renderRail();
    $("#title").textContent = item.name;
    $("#subtitle").textContent = "";
    $("#fold-all").hidden = true;
    $("#list").innerHTML = item.reason === "empty"
      ? `<div class="empty"><b>${esc(item.name)} 已安装，但里面还没有对话</b>有了对话之后再来看看。</div>`
      : `<div class="empty"><b>已经发现 ${esc(item.name)}</b>它的对话保存格式还没有公开，目前读不了，所以先不能搬。<br>已经安装、但这里不能搬的软件会一直列在左边，不会被漏掉。</div>`;
  }

  /* ----------------------------------------------------------- list */
  async function open(agentId, refresh = false) {
    state.current = agentId;
    state.selected = new Set();
    state.query = "";
    state.kind = "all";
    $("#search").value = "";
    updateBar();
    renderRail();
    const agent = state.agents.find((item) => item.id === agentId);
    $("#title").textContent = label(agent);
    $("#subtitle").textContent = agentId === "chatgpt" ? "正在从网页版读取，需要联网，可能要半分钟…" : "正在读取…";
    $("#fold-all").hidden = true;
    $("#list").innerHTML = '<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>';
    if (refresh || !state.cache[agentId] || agentId === "chatgpt") state.cache[agentId] = await call("sessions", agentId, refresh);
    if (state.current !== agentId) return;
    renderRail();
    renderList();
    refreshMemoryRecords();
    watchWeb(agentId, 0);
  }

  // ChatGPT shows its last saved cloud list at once and updates it in the background;
  // swap in the fresh list as soon as it is ready.
  async function watchWeb(agentId, tries) {
    const data = state.cache[agentId];
    if (!data || data.error || !data.web || !data.web.refreshing || tries >= 60) return;
    await new Promise((resolve) => setTimeout(resolve, 3000));
    if (state.current !== agentId) return;
    const next = await call("sessions", agentId, false);
    if (state.current !== agentId || !next || next.error) return;
    state.cache[agentId] = next;
    renderRail();
    renderList();
    watchWeb(agentId, tries + 1);
  }

  function visibleGroups() {
    const data = state.cache[state.current];
    if (!data || data.error) return [];
    const query = state.query.trim().toLowerCase();
    return data.groups
      .map((group) => ({
        ...group,
        sessions: group.sessions.filter(
          (item) =>
            (state.kind === "all" || !item.kind || item.kind === state.kind) &&
            (!query || item.title.toLowerCase().includes(query) || (group.title + group.path).toLowerCase().includes(query))
        ),
      }))
      .filter((group) => group.sessions.length || (group.keepEmpty && state.kind === "all" && (!query || (group.title + group.path).toLowerCase().includes(query))));
  }

  const groupKey = (group) => group.key || `${group.kind}|${group.path || group.title}`;

  // While searching every match is shown; folding then only lasts for that search.
  function foldSet() {
    if (state.query.trim()) return state.searchFolded;
    if (!state.folded[state.current]) {
      // a first look: folders holding many conversations start folded
      const data = state.cache[state.current];
      const initial = new Set();
      if (data && !data.error && data.groups.length > 1) {
        data.groups.forEach((group) => { if (group.sessions.length > 8) initial.add(groupKey(group)); });
      }
      state.folded[state.current] = initial;
    }
    return state.folded[state.current];
  }

  function renderFoldAll(groups) {
    const button = $("#fold-all");
    button.hidden = groups.length < 2;
    if (button.hidden) return;
    const fold = foldSet();
    const allFolded = groups.every((group) => fold.has(groupKey(group)));
    button.innerHTML = allFolded ? `${ICON.foldOut}<span>全部展开</span>` : `${ICON.foldIn}<span>全部收起</span>`;
  }

  function renderChips() {
    const data = state.cache[state.current];
    const box = $("#chips");
    const mixed = data && !data.error && data.groups.some((g) => g.sessions.some((s) => s.kind));
    box.hidden = !mixed;
    if (!mixed) return;
    const all = data.groups.flatMap((g) => g.sessions);
    const count = (k) => all.filter((s) => k === "all" || s.kind === k).length;
    box.innerHTML = [["all", "全部"], ["chat", "聊天"], ["work", "工作"], ["codex", "Codex"]]
      .map(([k, name]) => `<button class="chip ${state.kind === k ? "on" : ""}" data-kind="${k}">${name}<i>${count(k)}</i></button>`)
      .join("");
  }

  function renderList() {
    renderChips();
    const data = state.cache[state.current];
    const agent = state.agents.find((item) => item.id === state.current);
    if (!data) return;
    if (data.error) {
      $("#subtitle").textContent = "";
      $("#fold-all").hidden = true;
      $("#list").innerHTML = `<div class="empty"><b>读取没有成功</b>${esc(data.error)}</div>`;
      return;
    }
    const web = data.web;
    const webNote = web && web.refreshing ? "　云端聊天正在更新…"
      : web && web.age > 600 ? `　云端聊天是 ${Math.round(web.age / 60)} 分钟前的，点右上角刷新获取最新` : "";
    $("#subtitle").textContent = `${data.total} 条对话，其中 ${data.movable} 条可以搬运。归档和删除过的不显示。${webNote}`;
    const groups = visibleGroups();
    renderFoldAll(groups);
    if (!groups.length) {
      $("#list").innerHTML = `<div class="empty"><b>${state.query ? "没有找到匹配的对话" : "这里还没有对话"}</b>${state.query ? "换个关键词试试。" : agent.full + " 里没有可以显示的对话。"}</div>`;
      return;
    }
    const fold = foldSet();
    const sectionLabel = { pinned: "置顶", threads: "项目", projects: "项目" };
    let lastSection = "";
    $("#list").innerHTML = groups
      .map((group, gi) => {
        const movable = group.sessions.filter((item) => item.movable);
        const picked = movable.filter((item) => state.selected.has(item.id)).length;
        const mark = picked === 0 ? "" : picked === movable.length ? ICON.tick : ICON.dash;
        const klass = picked === 0 ? "" : picked === movable.length ? "on" : "part";
        const kind = group.kind === "none" ? (group.title === KIND.none ? "" : KIND.none) : KIND[group.kind] || "";
        const key = groupKey(group);
        const expanded = !fold.has(key);
        const sectionTitle = sectionLabel[group.section] || (group.section !== "chats" ? group.sectionTitle : "");
        const banner = group.section && group.section !== lastSection && sectionTitle
          ? `<div class="section-label">${esc(sectionTitle)}</div>` : "";
        if (group.section) lastSection = group.section;
        if (group.headless) {
          return `${banner}<div class="card">${group.sessions.map((item) => `<div class="row ${item.movable ? "" : "disabled"} ${state.selected.has(item.id) ? "selected" : ""}" data-id="${esc(item.id)}">
                  <span class="check">${ICON.tick}</span>
                  ${item.kind ? `<span class="kind ${item.kind}">${{chat: "聊天", work: "工作", codex: "Codex"}[item.kind] || ""}</span>` : ""}
                  <div class="row-main"><div class="row-title" title="${esc(item.title)}">${esc(item.title)}</div>${item.note ? `<div class="row-note">${esc(item.note)}</div>` : (item.folder ? `<div class="row-note">${esc(item.folder)}</div>` : "")}</div>
                  ${memoryBadge(item)}<span class="row-when">${esc(item.when)}</span>
                </div>`).join("")}</div>`;
        }
        return `${banner}<div class="group ${group.kind === "none" ? "group-none" : ""} ${expanded ? "" : "folded"}">
          <div class="group-head">
            ${movable.length ? `<button class="group-check" data-group="${gi}" aria-label="选择这一组"><span class="check ${klass}">${mark}</span></button>` : '<span class="group-check-gap"></span>'}
            <button class="group-fold" data-fold="${esc(key)}" aria-expanded="${expanded}" title="${expanded ? "收起" : "展开"}">
              <span class="chevron">${ICON.chevron}</span>
              <span class="group-icon">${GROUP_ICON[group.kind] || ICON.folder}</span>
              <span class="group-title" title="${esc(group.title)}">${esc(group.title)}</span>
              <span class="group-path" title="${esc(group.path || kind)}">${esc(group.path || kind)}</span>
              <span class="group-count">${group.sessions.length}</span>
            </button>
          </div>
          ${expanded ? `<div class="card">
            ${group.sessions
              .map(
                (item) => `<div class="row ${item.movable ? "" : "disabled"} ${state.selected.has(item.id) ? "selected" : ""}" data-id="${esc(item.id)}">
                  <span class="check">${ICON.tick}</span>
                  ${item.kind ? `<span class="kind ${item.kind}">${{chat: "聊天", work: "工作", codex: "Codex"}[item.kind] || ""}</span>` : ""}
                  <div class="row-main"><div class="row-title" title="${esc(item.title)}">${esc(item.title)}</div>${item.note ? `<div class="row-note">${esc(item.note)}</div>` : (item.folder && (group.kind === "recent" || group.kind === "task") ? `<div class="row-note">${esc(item.folder)}</div>` : "")}</div>
                  ${memoryBadge(item)}<span class="row-when">${esc(item.when)}</span>
                </div>`
              )
              .join("")}
          </div>` : ""}
        </div>`;
      })
      .join("");
  }

  function toggle(id) {
    if (state.selected.has(id)) state.selected.delete(id);
    else state.selected.add(id);
  }

  function updateBar() {
    const count = state.selected.size;
    $("#bar").hidden = count === 0;
    $("#bar-count").textContent = count;
    const agent = state.agents.find((item) => item.id === state.current);
    $("#bar-text").textContent = `条已选${agent ? "，来自 " + agent.full : ""}`;
  }

  /* ---------------------------------------------------------- sheet */
  const STEP_NAMES = ["软件", "文件夹", "确认"];

  function openSheet() {
    state.sheet = { step: 0, mode: state.smartTargets.length ? "smart" : "full", product: null, target: null, directory: "", folders: null, folderQuery: "", job: null, busy: false, factUpdates: {} };
    $("#sheet").hidden = false;
    renderSheet();
  }

  function closeSheet() {
    if (state.sheet && state.sheet.busy) return;
    $("#sheet").hidden = true;
    state.sheet = null;
  }

  function selectedSessions() {
    const data = state.cache[state.current];
    const map = new Map();
    data.groups.forEach((group) => group.sessions.forEach((item) => map.set(item.id, item)));
    return [...state.selected].map((id) => map.get(id)).filter(Boolean);
  }

  function sharedFolder() {
    if (state.sheet?.fromMemory) return "";
    const folders = new Set(selectedSessions().map((item) => item.folder).filter(Boolean));
    const empty = selectedSessions().some((item) => !item.folder);
    return folders.size === 1 && !empty ? [...folders][0] : "";
  }

  function stepsHtml(step) {
    const names = state.sheet?.mode === "smart" ? ["选择软件", "确认搬家"] : STEP_NAMES;
    return names.map((name, i) => `<li class="${i === step ? "on" : i < step ? "done" : ""}" ${i === step ? 'aria-current="step"' : ""}><i>${i + 1}</i>${name}</li>`).join("");
  }

  function renderSheet() {
    const sheet = state.sheet;
    if (!sheet) return;
    const finished = sheet.step >= 3;
    const completedMemory = sheet.mode === "smart" && sheet.smartStage === "done";
    $(".sheet-panel").classList.toggle("memory-complete", completedMemory);
    $("#steps").innerHTML = sheet.mode === "memory-detail" || completedMemory ? "" : sheet.mode === "smart" ? stepsHtml(sheet.step ? 1 : 0) : finished ? "" : stepsHtml(sheet.step);
    $("#sheet-back").disabled = sheet.mode === "memory-detail" || (sheet.step === 0 && !sheet.product) || finished || sheet.busy;
    const body = $("#sheet-body");
    body.classList.toggle("memory-view", sheet.mode === "smart" || sheet.mode === "memory-detail");
    const screen = `${sheet.mode}:${sheet.step}:${sheet.smartStage || ""}:${sheet.product || ""}`;
    if (screen !== sheet.renderedScreen) { body.scrollTop = 0; sheet.renderedScreen = screen; }
    if (sheet.mode === "memory-detail") { renderMemoryTools(body); return; }
    if (sheet.mode === "smart" && sheet.step >= 3) { renderSmart(body); return; }
    if (sheet.step === 0) renderTargets(body);
    else if (sheet.step === 1) renderFolders(body);
    else if (sheet.step === 2) renderConfirm(body);
    else renderRun(body);
    if (sheet.step === 0 && state.smartTargets.length && !sheet.fromMemory) {
      body.insertAdjacentHTML("afterbegin", `<div class="memory-mode" role="group" aria-label="迁移方式"><button class="btn ${sheet.mode === "smart" ? "primary" : "plain"}" data-migrate-mode="smart">智能省额度迁移</button><button class="btn ${sheet.mode === "full" ? "primary" : "plain"}" data-migrate-mode="full">完整对话迁移</button></div>`);
      body.querySelectorAll("[data-migrate-mode]").forEach(button => { button.onclick = () => {
        sheet.mode = button.dataset.migrateMode; sheet.target = null; sheet.product = null; sheet.folders = null; renderSheet();
      }; });
    }
  }

  function renderTargets(body) {
    if (state.sheet.mode === "smart") {
      body.innerHTML = `<h2>把旧对话带到 Copilot，接着聊</h2><p class="lead">已选 ${state.selected.size} 条对话。完整记录保存在本机，聊天时只查需要的部分。</p>
        <div class="choices">${state.smartTargets.map(targetHtml).join("")}</div>
        <p class="hint">每条对话单独保存，已有项目保持原样。</p>
        <details class="memory-help"><summary>和完整对话迁移有什么区别？</summary><p>智能搬家会保存完整旧记录，供 Copilot 按需查找。完整对话迁移会把旧消息复制到目标软件的对话里。</p><p>准备过程不使用 AI 额度；之后聊天按 Copilot 的正常用量计算，能节省多少取决于实际使用。</p></details>`;
      bindTargets(body);
      return;
    }
    const product = state.sheet.product;
    if (product) {
      const name = product === "chatgpt" ? "ChatGPT" : "Claude";
      const options = state.targets.filter((agent) => agent.product === product).sort((left, right) => Number(right.canTarget) - Number(left.canTarget));
      body.innerHTML = `<h2>搬进 ${name} 的哪里？</h2><p class="lead">本机任务可以搬入，普通云端聊天只支持搬出。请选择具体模式。</p>
        <div class="choices choices-modes">${options.map(targetHtml).join("")}</div>`;
      bindTargets(body);
      return;
    }
    const shown = new Set();
    const cards = state.targets.map((agent) => {
      if (!agent.product) return targetHtml(agent);
      if (shown.has(agent.product)) return "";
      shown.add(agent.product);
      const options = state.targets.filter((item) => item.product === agent.product);
      const enabled = options.some((item) => item.canTarget);
      const name = agent.product === "chatgpt" ? "ChatGPT" : "Claude";
      const description = agent.product === "chatgpt" ? "选择本机 Work 或 Codex" : "选择本机 Cowork 或 Claude Code";
      return `<button class="choice product-choice" data-product="${agent.product}">
        ${agentLogo(agent.product, name)}
        <span class="choice-copy"><b>${name}</b><small>${enabled ? description : "查看可用模式与限制"}</small></span>${ICON.chevron}
      </button>`;
    }).join("");
    body.innerHTML = `<h2>搬到哪个软件？</h2><p class="lead">已选 ${state.sheet.fromMemory ? state.sheet.memoryStatus.items.length : state.selected.size} 条对话。点一下目的地。</p>
      <div class="choices">${cards}</div>`;
    body.querySelectorAll("[data-product]").forEach((button) => {
      button.onclick = () => { state.sheet.product = button.dataset.product; renderSheet(); };
    });
    bindTargets(body);
  }

  function targetHtml(agent) {
    const ok = agent.canTarget;
    return `<button class="choice ${state.sheet.target === agent.id ? "on" : ""}" data-target="${agent.id}" ${ok ? "" : "disabled"}>
      ${agentLogo(agent.id, agent.name)}
      <span class="choice-copy"><b>${esc(agent.name)}</b><small>${esc(ok ? agent.targetSub || agent.sub : agent.readOnlyReason || "当前版本没有写入实现")}</small></span>
    </button>`;
  }

  function bindTargets(body) {
    body.querySelectorAll("[data-target]").forEach((button) => {
      button.onclick = () => {
        state.sheet.target = button.dataset.target;
        if (state.sheet.mode === "smart") { startMemory(); return; }
        state.sheet.step = 1;
        loadFolders();
        renderSheet();
      };
    });
  }

  function backSheet() {
    const sheet = state.sheet;
    if (!sheet || sheet.busy || sheet.step >= 3) return;
    if (sheet.step > 0) sheet.step -= 1;
    else if (sheet.product) sheet.product = null;
    else { closeSheet(); return; }
    renderSheet();
  }

  async function loadFolders() {
    const sheet = state.sheet;
    if (sheet.folders) return;
    sheet.folders = [];
    sheet.loadingFolders = true;
    const list = await call("folders");
    if (state.sheet !== sheet) return;
    sheet.folders = list;
    sheet.loadingFolders = false;
    if (sheet.step === 1) renderSheet();
  }

  function renderFolders(body) {
    const sheet = state.sheet;
    const target = state.targets.find((item) => item.id === sheet.target);
    const same = sharedFolder();
    const query = sheet.folderQuery.trim().toLowerCase();
    const items = (sheet.folders || []).filter((item) => !query || (item.name + item.path).toLowerCase().includes(query));
    const entry = (path, name, tag) => `<button class="folder ${sheet.directory === path ? "on" : ""}" data-path="${esc(path)}">
        ${ICON.folder}<span style="min-width:0;flex:1"><div class="folder-name">${esc(name)}${tag ? ` <small style="color:var(--accent);font-weight:600">${tag}</small>` : ""}</div><div class="folder-path">${esc(path)}</div></span></button>`;
    const chosenExtra = sheet.directory && !(sheet.folders || []).some((item) => item.path === sheet.directory) && sheet.directory !== same
      ? entry(sheet.directory, sheet.directory.split(/[\\/]/).filter(Boolean).pop() || sheet.directory, "新选的") : "";
    body.innerHTML = `<h2>放进哪个文件夹？</h2><p class="lead">${esc(target.folderHint || "选择导入记录使用的工作目录，不会复制项目文件。")}</p>
      ${target.notice ? `<div class="import-notice">${esc(target.notice)}</div>` : ""}
      <div class="folder-search">
        <label class="search">${'<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>'}<input id="folder-q" type="search" placeholder="搜索文件夹" value="${esc(sheet.folderQuery)}" /></label>
        <button id="pick" class="btn plain">选择或新建…</button>
      </div>
      <div class="folder-list">
        ${same ? entry(same, same.split(/[\\/]/).filter(Boolean).pop() || same, "和原来一样") : ""}
        ${chosenExtra}
        ${sheet.loadingFolders ? '<div class="loading"><div class="spinner"></div>正在整理文件夹…</div>' : items.filter((item) => item.path !== same).map((item) => entry(item.path, item.name, "")).join("")}
        ${!sheet.loadingFolders && !items.length && !same && !chosenExtra ? '<div class="empty" style="padding:30px 0">没有找到，点右上「选择或新建…」。</div>' : ""}
      </div>
      <div class="foot"><span class="hint">${sheet.directory ? esc(sheet.directory) : "还没有选文件夹"}</span><button id="next" class="btn primary" ${sheet.directory ? "" : "disabled"}>下一步</button></div>`;
    body.querySelectorAll("[data-path]").forEach((button) => {
      button.onclick = () => { sheet.directory = button.dataset.path; renderSheet(); };
    });
    const input = body.querySelector("#folder-q");
    input.oninput = () => {
      sheet.folderQuery = input.value;
      const pos = input.selectionStart;
      renderSheet();
      const again = $("#folder-q");
      again.focus();
      again.setSelectionRange(pos, pos);
    };
    body.querySelector("#pick").onclick = async () => {
      const chosen = await call("pick_folder");
      if (chosen) { sheet.directory = chosen; renderSheet(); }
    };
    const next = body.querySelector("#next");
    if (next) next.onclick = () => { sheet.step = 2; renderSheet(); };
  }

  function renderConfirm(body) {
    const sheet = state.sheet;
    const source = state.agents.find((item) => item.id === state.current);
    const target = state.targets.find((item) => item.id === sheet.target);
    body.innerHTML = `<h2>确认一下</h2><p class="lead">原来的记录会原样保留，这里只是复制一份过去。</p>
      <div class="summary"><dl>
        <div class="line"><dt>从</dt><dd>${esc(sheet.fromMemory ? "已保存的旧对话" : source.full)}</dd></div>
        <div class="line"><dt>对话</dt><dd>${sheet.fromMemory ? sheet.memoryStatus.items.length : state.selected.size} 条</dd></div>
        <div class="line"><dt>搬到</dt><dd>${esc(target.full)}</dd></div>
        <div class="line"><dt>文件夹</dt><dd>${esc(sheet.directory)}</dd></div>
      </dl></div>
      ${target.notice ? `<div class="import-notice">${esc(target.notice)}</div>` : ""}
      <div class="foot"><span class="hint">搬运过程中请不要关闭本软件</span><button id="go" class="btn primary">开始搬运</button></div>`;
    body.querySelector("#go").onclick = startMove;
  }

  async function startMove() {
    cancelMemoryOpen();
    const sheet = state.sheet;
    const result = sheet.fromMemory
      ? await call("start_full_from_memory", sheet.target, sheet.directory)
      : await call("start_move", state.current, [...state.selected], sheet.target, sheet.directory);
    if (result.error) { toast(result.error); return; }
    sheet.step = 3;
    sheet.busy = true;
    sheet.status = { total: result.total, done: 0, items: [] };
    renderSheet();
    poll();
  }

  async function startMemory() {
    const sheet = state.sheet;
    if (sheet.busy) return;
    cancelMemoryOpen();
    sheet.desktopOpenState = null; sheet.confirmRollback = false; sheet.factUpdates = {};
    sheet.step = 3; sheet.busy = true; sheet.smartStage = "preparing";
    sheet.memoryStatus = {total: state.selected.size, done: 0, items: []}; renderSheet();
    const result = await call("prepare_memory", state.current, [...state.selected], sheet.target);
    if (result.error) { sheet.busy = false; sheet.step = 0; sheet.smartStage = null; renderSheet(); toast(result.error); return; }
    sheet.memoryStatus = {total: result.total, done: 0, items: []}; renderSheet();
    pollMemory(sheet);
  }

  async function pollMemory(sheet) {
    if (state.sheet !== sheet) return;
    sheet.memoryStatus = await call("memory_status");
    if (sheet.memoryStatus.finished) {
      sheet.busy = false; sheet.smartStage = "review";
      if (!sheet.memoryStatus.failed) sheet.plan = await call("memory_plan");
    }
    if (state.sheet !== sheet) return;
    renderSheet();
    if (!sheet.memoryStatus.finished) setTimeout(() => pollMemory(sheet), 450);
  }

  function memoryRole(role) {
    return ({user: "你说的", assistant: "AI 的回复", system: "系统说明", tool: "工具记录"})[role] || "其他记录";
  }

  function renderSmart(body) {
    const sheet = state.sheet;
    if (sheet.smartStage === "preparing" || sheet.smartStage === "deploying") {
      const status = sheet.memoryStatus || {done: 0, total: 0, items: []};
      const adding = sheet.smartStage === "deploying";
      const percent = status.total ? Math.round(status.done / status.total * 100) : 0;
      body.innerHTML = `<h2>${adding ? "正在搬家…" : "正在保存旧对话…"}</h2>
        <p class="lead">${adding ? "正在创建独立的资料项目，已有项目保持原样。" : "完整保留原文，准备好后再让你确认。"}</p>
        <div class="progress-bar ${adding ? "memory-progress-wait" : ""}" role="progressbar" aria-label="${adding ? "正在搬家" : "正在保存旧对话"}" ${adding ? "" : `aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent}"`}><i style="width:${adding ? 35 : percent}%"></i></div>
        <p class="hint" role="status">${adding ? "请稍等…" : `已保存 ${status.done || 0} / ${status.total || 0} 条对话`} · 准备过程不使用 AI 额度</p>`;
      return;
    }
    if (sheet.smartStage === "done") { renderMemoryDone(body); return; }
    const status = sheet.memoryStatus;
    const plan = sheet.plan;
    const failed = status?.failed || plan?.error;
    const existingIssue = plan?.error_stage === "existing-entry";
    body.innerHTML = `<h2>${existingIssue ? "原搬家记录需要核对" : failed ? "还有一些记录没准备好" : "准备好了，可以搬家了"}</h2>
      <p class="lead">${existingIssue ? "原来的对话和资料都已保留，没有重复创建。" : failed ? "已有项目没有改动，可以返回重试。" : "每条对话保留原名称；搬过的会沿用原入口，已有项目保持原样。"}</p>
      ${failed ? `<div class="import-notice" role="alert">${esc(plan?.error || "部分对话未能完整保存，请返回后重试。")}</div>` : ""}
      ${plan?.ok ? `<div class="memory-card memory-destination"><span class="memory-eyebrow">搬到 Copilot 桌面端</span>${(plan.entries || [plan]).map(item => `<b>${esc(item.desktop_title)}</b>`).join("")}<p class="hint">${plan.reused_count ? `其中 ${plan.reused_count} 条已搬过，不会重复创建。` : "完整旧记录已保存，聊天时按需查找。"}</p></div>` : ""}
      <div class="foot"><button class="btn plain" id="memory-back">返回</button><button class="btn primary" id="memory-deploy" ${!plan?.ok ? "disabled" : ""}>开始搬家</button></div>`;
    body.querySelector("#memory-back").onclick = () => { sheet.step = 0; sheet.smartStage = null; renderSheet(); };
    body.querySelector("#memory-deploy").onclick = async () => {
      sheet.busy = true; sheet.smartStage = "deploying"; renderSheet();
      const result = await call("deploy_memory");
      sheet.busy = false;
      if (result.error) { sheet.smartStage = "review"; sheet.plan = await call("memory_plan"); toast(result.error); }
      else { sheet.smartStage = "done"; sheet.deployment = result; }
      renderSheet();
      refreshMemoryRecords();
      if (!result.error) requestMemoryOpen(sheet);
    };
  }

  function memoryFactsHtml(sheet) {
    const items = (sheet.memoryStatus?.items || []).filter(item => item.facts?.length);
    if (!items.length) return "";
    return `<details class="memory-facts"><summary>以后需要一直遵守的要求（选用）</summary><p class="hint">只有你确认的内容才会作为要求；其余旧话只是参考，不用逐条处理。</p>${items.map(item => `<div class="memory-history"><b>${esc(item.title)}</b>${item.facts.map(fact => {
      const value = sheet.factUpdates[item.bundle]?.find(i => i.id === fact.id)?.status || fact.status;
      return `<div class="memory-fact"><p>${esc(fact.content)}</p><select aria-label="这条要求现在还适用吗" data-fact="${esc(fact.id)}" data-bundle="${item.bundle}"><option value="candidate" ${value === "candidate" ? "selected" : ""}>仅作参考</option><option value="confirmed" ${value === "confirmed" ? "selected" : ""}>以后继续遵守</option><option value="superseded" ${value === "superseded" ? "selected" : ""}>已经不用了</option></select></div>`;
    }).join("")}${item.facts_total > item.facts.length ? '<p class="hint">先显示前 100 条，其余内容仍保存在完整原文里。</p>' : ""}</div>`).join("")}<button class="btn plain" id="memory-facts-save">保存要求</button><span class="hint" id="memory-facts-note" role="status"></span></details>`;
  }

  function renderMemoryDone(body) {
    const sheet = state.sheet;
    const opening = sheet.desktopOpenState === null || sheet.desktopOpenState === "opening";
    const error = sheet.desktopOpenState?.error;
    const pending = sheet.desktopOpenState?.pending;
    body.innerHTML = `<div class="done-mark">${ICON.tick.replace(/13/g, "26")}</div><h2>${opening ? "正在完成搬家" : pending || error ? "旧对话已保存" : "搬好了"}</h2>
      <p class="lead" role="status">${opening ? "正在让 Copilot 左侧列表显示新对话…" : error ? esc(sheet.desktopOpenState.error) : pending ? (sheet.desktopOpenState.refresh_status === "draft" ? "Copilot 里还有未发送的内容，先为你保留。处理完后会自动显示新对话。" : "Copilot 正在工作，任务结束后会自动显示新对话。") : "在 Copilot 中输入下一步想做的事，就能接着聊。"}</p>
      <div class="memory-card memory-destination"><span class="memory-eyebrow">Copilot 中的对话${sheet.deployment.reused_count ? " · 已搬过的沿用原记录" : ""}</span>${(sheet.deployment.entries || [sheet.deployment]).map(item => `<b>${esc(item.desktop_title)}</b>`).join("")}</div>
      ${error ? '<p class="hint">可以重试打开，或稍后在 Copilot 左侧的新资料项目里找到这条对话。</p><button class="btn plain" id="memory-open">重试打开 Copilot</button>' : ""}
      <div class="foot"><span class="hint">原来的记录和已有项目都保留</span><button class="btn primary" id="memory-finish">完成</button></div>`;
    body.querySelector("#memory-open")?.addEventListener("click", () => requestMemoryOpen(sheet));
    body.querySelector("#memory-finish").onclick = () => { closeSheet(); state.selected = new Set(); updateBar(); renderList(); refreshMemoryRecords(); };
  }

  function cancelMemoryOpen() {
    clearTimeout(state.memoryOpenTimer);
    state.memoryOpenGeneration = (state.memoryOpenGeneration || 0) + 1;
  }

  async function requestMemoryOpen(sheet) {
    if (sheet.openInFlight) return;
    sheet.openInFlight = true;
    const generation = state.memoryOpenGeneration;
    const before = JSON.stringify(sheet.desktopOpenState);
    if (!sheet.desktopOpenState?.pending) sheet.desktopOpenState = "opening";
    clearTimeout(state.memoryOpenTimer);
    if (state.sheet === sheet && sheet.mode !== "memory-detail" && !sheet.desktopOpenState?.pending) renderSheet();
    try { sheet.desktopOpenState = await call("open_memory_desktop", sheet.deployment.id); }
    catch (_) { sheet.desktopOpenState = {error: "旧对话已保存，暂时无法打开 Copilot，请稍后重试。"}; }
    sheet.openInFlight = false;
    if (state.sheet === sheet) {
      if (sheet.mode !== "memory-detail") { if (before !== JSON.stringify(sheet.desktopOpenState)) renderSheet(); }
      else {
        const note = $("#memory-open-note");
        if (note) note.textContent = sheet.desktopOpenState.error || (sheet.desktopOpenState.pending ? "旧记录已保存，等待 Copilot 空闲后自动显示。" : "已请求 Copilot 更新列表并打开对话。");
      }
    }
    if (sheet.desktopOpenState?.pending && generation === state.memoryOpenGeneration) state.memoryOpenTimer = setTimeout(() => requestMemoryOpen(sheet), 3000);
  }

  async function refreshMemoryRecords() {
    if (!state.smartTargets.length) return;
    try {
      const result = await call("memory_records");
      if (result.error) return;
      state.memoryRecords = (result.items || []).sort((a,b) => Number(b.desktop_available === true) - Number(a.desktop_available === true) || (a.sources?.length || 0) - (b.sources?.length || 0) || a.timestamp - b.timestamp);
      if (state.current && state.cache[state.current]) renderList();
    } catch (_) { /* Older preview bridges do not provide saved-entry metadata. */ }
  }

  function memoryBadge(item) {
    const record = state.memoryRecords.find(record => record.sources?.some(source => source.id === item.id && source.source === (item.source || state.current)));
    return record ? `<span class="memory-saved-actions"><button class="memory-saved" data-memory-open="${record.id}" title="在 Copilot 中查看">已智能搬家</button><button class="memory-more" data-memory-tools="${record.id}" aria-label="这条对话的更多操作" title="更多操作">···</button></span>` : "";
  }

  async function openSavedMemory(identity, tools) {
    if (state.sheet || state.memorySelecting) return;
    state.memorySelecting = true;
    cancelMemoryOpen();
    let result;
    try { result = await call("select_memory_record", identity); }
    finally { state.memorySelecting = false; }
    if (result.error) { toast(result.error); return; }
    const sheet = {mode: "memory-detail", step: 3, busy: false, record: identity, deployment: result.deployment,
      memoryStatus: {items: result.items}, factUpdates: {}, desktopOpenState: null, folderQuery: "", directory: ""};
    if (tools) { state.sheet = sheet; $("#sheet").hidden = false; renderSheet(); }
    else {
      await requestMemoryOpen(sheet);
      if (sheet.desktopOpenState?.error) toast(sheet.desktopOpenState.error);
      else if (sheet.desktopOpenState?.pending) toast("记录已保留，Copilot 空闲后会自动打开");
    }
  }

  function renderMemoryTools(body) {
    const sheet = state.sheet;
    const done = sheet.deployment;
    body.innerHTML = `<h2>${esc(done.desktop_title)}</h2><p class="lead">${esc(done.project_name)}</p>
        <button class="btn primary" id="memory-open">在 Copilot 中查看</button>
        <p class="hint" role="status" id="memory-open-note"></p>
        <details class="memory-card" id="memory-browser"><summary>查看保存的旧对话</summary><div class="memory-search"><input id="memory-query" type="search" aria-label="搜索旧对话" placeholder="输入你记得的关键词" value="${esc(sheet.historyQuery || "")}"/><button class="btn plain" id="memory-search">搜索</button></div><div id="memory-hits" aria-live="polite"></div><div id="memory-read"></div></details>
        ${memoryFactsHtml(sheet)}
        <div class="memory-actions"><button class="btn plain" id="memory-folder">打开旧记录保存位置</button><button class="btn plain" id="memory-full">改用完整对话迁移</button></div>
        ${sheet.confirmRollback ? '<div class="import-notice">撤销会移除这次新增的对话和资料设置，工具箱保存的完整旧记录仍保留。如果你已接着聊或修改过相关内容，会停止撤销以保护后续工作。<div class="memory-actions"><button class="btn plain" id="memory-rollback-cancel">先不撤销</button><button class="btn plain memory-danger" id="memory-rollback-confirm">确认撤销这次搬家</button></div></div>' : '<button class="btn plain" id="memory-rollback">撤销这次搬家</button>'}
      <div class="foot"><button class="btn plain" id="memory-record-back">关闭</button></div>`;
    body.querySelector("#memory-open").onclick = () => requestMemoryOpen(sheet);
    body.querySelector("#memory-folder").onclick = async () => { const r = await call("open_memory_folder"); if (r.error) toast(r.error); };
    body.querySelector("#memory-full").onclick = () => { sheet.mode = "full"; sheet.fromMemory = true; sheet.step = 0; sheet.target = null; sheet.product = null; sheet.directory = ""; renderSheet(); };
    body.querySelector("#memory-record-back").onclick = closeSheet;
    body.querySelectorAll("[data-fact]").forEach(select => { select.onchange = () => {
      const changes = sheet.factUpdates[select.dataset.bundle] ||= [];
      const item = changes.find(i => i.id === select.dataset.fact);
      if (item) item.status = select.value; else changes.push({id: select.dataset.fact, status: select.value});
    }; });
    const saveFacts = body.querySelector("#memory-facts-save");
    if (saveFacts) saveFacts.onclick = async () => {
      saveFacts.disabled = true;
      const result = await call("confirm_memory_facts", sheet.factUpdates);
      body.querySelector("#memory-facts-note").textContent = result.error || "已保存";
      saveFacts.disabled = false;
    };
    const rollback = body.querySelector("#memory-rollback");
    if (rollback) rollback.onclick = () => { sheet.confirmRollback = true; renderSheet(); };
    const cancel = body.querySelector("#memory-rollback-cancel");
    if (cancel) cancel.onclick = () => { sheet.confirmRollback = false; renderSheet(); };
    const confirm = body.querySelector("#memory-rollback-confirm");
    if (confirm) confirm.onclick = async () => {
      cancelMemoryOpen();
      confirm.disabled = true;
      const r = await call("rollback_memory");
      if (r.error) { toast(r.error); confirm.disabled = false; }
      else { closeSheet(); refreshMemoryRecords(); toast("这次搬家已撤销，工具箱里的旧记录仍保留"); }
    };
    const search = async () => {
      const query = body.querySelector("#memory-query").value;
      sheet.historyQuery = query;
      const result = await call("search_memory", query);
      const hits = body.querySelector("#memory-hits");
      if (result.error) { toast(result.error); return; }
      hits.innerHTML = result.hits.length ? result.hits.map(h => `<button class="memory-hit" data-message="${esc(h.message_id)}"><b>${memoryRole(h.role)}</b><p>${esc(h.snippet)}</p><small>查看这条消息的完整原文</small></button>`).join("") : '<p class="hint">没有找到相关内容，换个关键词试试。</p>';
      hits.querySelectorAll("[data-message]").forEach(button => { button.onclick = () => showMemoryMessage(body, button.dataset.message, 0); });
    };
    body.querySelector("#memory-search").onclick = search;
    body.querySelector("#memory-query").onkeydown = event => { if (event.key === "Enter") search(); };
  }

  async function showMemoryMessage(body, message, offset) {
    const result = await call("read_memory", message, offset);
    if (result.error) { toast(result.error); return; }
    const panel = body.querySelector("#memory-read");
    if (!offset) panel.innerHTML = `<h3>完整原文 · ${memoryRole(result.role)}</h3><pre></pre><details class="memory-reference"><summary>查看消息编号</summary><small>${esc(result.id)}</small></details>`;
    panel.querySelector("pre").textContent += result.content;
    panel.querySelector("button")?.remove();
    if (result.next_offset !== null) {
      const more = document.createElement("button"); more.className = "btn plain"; more.textContent = "显示后面的内容";
      more.onclick = () => showMemoryMessage(body, message, result.next_offset); panel.appendChild(more);
    }
    if (!offset) { panel.tabIndex = -1; panel.focus({preventScroll: true}); panel.scrollIntoView({block: "start"}); }
  }

  async function poll() {
    const sheet = state.sheet;
    if (!sheet) return;
    const status = await call("move_status");
    sheet.status = status;
    if (status.finished) sheet.busy = false;
    if (state.sheet === sheet) renderSheet();
    if (!status.finished) setTimeout(poll, 450);
    else if (!sheet.autoOpened) {
      sheet.autoOpened = true;
      let last = -1;
      status.items.forEach((item, index) => { if (canOpenResult(item, sheet)) last = index; });
      if (last >= 0) {
        const result = await call("open_in_app", last);
        sheet.openRequest = { index: last, error: result && result.error, refreshed: result && result.refreshed };
        if (state.sheet === sheet) renderSheet();
        if (result && result.error) toast(result.error);
      }
    }
  }

  function canOpenResult(item, sheet) {
    return item.openUrl && (item.state === "ok" || (sheet.target === "copilot_desktop" && item.state === "skipped"));
  }

  function renderRun(body) {
    const sheet = state.sheet;
    const status = sheet.status;
    const target = state.targets.find((item) => item.id === sheet.target);
    if (!status.finished) {
      const percent = status.total ? Math.round((status.done / status.total) * 100) : 0;
      body.innerHTML = `<h2>正在搬运…</h2><p class="lead">请稍等，不要关闭软件。</p>
        <div class="progress-bar"><i style="width:${percent}%"></i></div>
        <div class="progress-text">${status.done} / ${status.total}</div>`;
      return;
    }
    const bad = status.failed > 0;
    const copilot = sheet.target === "copilot_desktop";
    const openName = copilot ? "Copilot" : "ChatGPT";
    const openPending = copilot ? "在 Copilot 查看搬入的聊天" : "可请求 ChatGPT 打开这条本机记录";
    const openRequested = copilot ? (sheet.openRequest?.refreshed ? "已刷新 Copilot，最新复制的聊天在列表顶部" : "已请求打开 Copilot 会话列表") : "已请求打开这条记录；请在 ChatGPT 中确认";
    const hint = target.resultHint || "已写入目标软件的本机记录。";
    body.innerHTML = `<div class="done-mark ${bad ? "warn" : ""}">${bad ? ICON.dash.replace(/13/g, "26") : ICON.tick.replace(/13/g, "26")}</div>
      <h2>${bad ? (status.ok ? "部分记录未复制成功" : "这次没有复制成功") : (!status.ok && status.skipped ? "这些记录之前已复制" : "记录已复制")}</h2>
      <p class="lead">成功 ${status.ok} 条${status.skipped ? `，已搬过 ${status.skipped} 条` : ""}${bad ? `，没成功 ${status.failed} 条` : ""}。${status.ok || (copilot && status.skipped) ? hint : ""}</p>
      ${status.ok ? '<p class="hint" data-verification-scope>已确认记录写入后能够重新读取；目标软件是否显示、能否继续对话，仍需在对应软件确认。项目文件、附件和运行环境不会一起复制。</p>' : ""}
      ${status.items.length ? `<div class="results">${status.items.map((item, index) => `<div class="result ${item.state}"><div class="result-heading"><span class="t">${esc(item.title)}</span><span class="m">${esc(item.message)}</span></div>
        ${item.resumeCommand ? `<label class="resume-label">打开记录命令（在所选文件夹执行）<input readonly value="${esc(item.resumeCommand)}" aria-label="续聊命令" /></label>` : ""}
        ${canOpenResult(item, sheet) ? `<div class="result-location"><span>${sheet.openRequest?.index === index ? (sheet.openRequest.error ? "记录已复制，打开软件失败；可以重试" : openRequested) : openPending}</span><button class="btn plain small" data-open-app="${index}">在 ${openName} 中${copilot ? "查看" : "打开"}</button></div>` : ""}
        ${item.location && item.state === "ok" ? `<div class="result-location"><span>${esc(item.location)}</span><button class="btn plain small" data-import-folder="${index}">查看位置</button></div>` : ""}</div>`).join("")}</div>` : ""}
      <div class="foot"><span class="hint">${esc(sheet.directory)}</span><button id="finish" class="btn primary">完成</button></div>`;
    body.querySelector("#finish").onclick = () => {
      closeSheet();
      state.selected = new Set();
      updateBar();
      renderList();
    };
    body.querySelectorAll("[data-open-app]").forEach((button) => {
      button.onclick = async () => {
        const result = await call("open_in_app", Number(button.dataset.openApp));
        sheet.openRequest = { index: Number(button.dataset.openApp), error: result && result.error, refreshed: result && result.refreshed };
        if (state.sheet === sheet) renderSheet();
        if (result.error) toast(result.error);
      };
    });
    body.querySelectorAll("[data-import-folder]").forEach((button) => {
      button.onclick = async () => {
        const result = await call("open_import_folder", Number(button.dataset.importFolder));
        if (result.error) toast(result.error);
      };
    });
  }

  /* ----------------------------------------------------------- wiring */
  function wire() {
    $("#agents").addEventListener("click", (event) => {
      const extra = event.target.closest("[data-extra]");
      if (extra) { showExtra(extra.dataset.extra); return; }
      const button = event.target.closest("[data-agent]");
      if (button) open(button.dataset.agent);
    });
    $("#list").addEventListener("click", (event) => {
      const saved = event.target.closest("[data-memory-open], [data-memory-tools]");
      if (saved) { openSavedMemory(saved.dataset.memoryOpen || saved.dataset.memoryTools, !!saved.dataset.memoryTools); return; }
      const groupButton = event.target.closest("[data-group]");
      if (groupButton) {
        const group = visibleGroups()[Number(groupButton.dataset.group)];
        const movable = group.sessions.filter((item) => item.movable);
        const all = movable.every((item) => state.selected.has(item.id));
        movable.forEach((item) => (all ? state.selected.delete(item.id) : state.selected.add(item.id)));
        updateBar();
        renderList();
        return;
      }
      const foldButton = event.target.closest("[data-fold]");
      if (foldButton) {
        const fold = foldSet();
        const key = foldButton.dataset.fold;
        if (fold.has(key)) fold.delete(key);
        else fold.add(key);
        const keep = $("#list").scrollTop;
        renderList();
        $("#list").scrollTop = keep;
        return;
      }
      const row = event.target.closest(".row");
      if (!row || row.classList.contains("disabled")) return;
      toggle(row.dataset.id);
      row.classList.toggle("selected", state.selected.has(row.dataset.id));
      updateBar();
      const keep = $("#list").scrollTop;
      renderList();
      $("#list").scrollTop = keep;
    });
    $("#chips").addEventListener("click", (event) => {
      const chip = event.target.closest("[data-kind]");
      if (!chip) return;
      state.kind = chip.dataset.kind;
      renderList();
    });
    $("#search").addEventListener("input", (event) => {
      state.query = event.target.value;
      state.searchFolded = new Set();
      renderList();
    });
    $("#fold-all").addEventListener("click", () => {
      const groups = visibleGroups();
      const fold = foldSet();
      const allFolded = groups.every((group) => fold.has(groupKey(group)));
      groups.forEach((group) => (allFolded ? fold.delete(groupKey(group)) : fold.add(groupKey(group))));
      renderList();
    });
    $("#reload").addEventListener("click", refresh);
    $("#bar-clear").addEventListener("click", () => { state.selected = new Set(); updateBar(); renderList(); });
    $("#bar-go").addEventListener("click", openSheet);
    $("#sheet").addEventListener("click", (event) => { if (event.target.closest("[data-close]")) closeSheet(); });
    $("#sheet-back").addEventListener("click", () => {
      backSheet();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || !state.sheet) return;
      if (state.sheet.step >= 3) closeSheet();
      else backSheet();
    });
  }

  async function discoverAgents() {
    const info = await call("agents");
    state.agents = info.agents;
    state.agents.forEach((agent) => { agent.full = state.agents.filter((item) => item.name === agent.name).length > 1 ? `${agent.name} ${agent.sub}` : agent.name; });
    state.targets = info.targets || info.agents.filter(agent => !agent.sourceOnly);
    state.smartTargets = info.smartTargets || [];
    state.targets.forEach((agent) => { agent.full = state.targets.filter((item) => item.name === agent.name).length > 1 ? `${agent.name} ${agent.sub}` : agent.name; });
    state.unsupported = info.unsupported || [];
    renderRail();
    return info;
  }

  async function refresh() {
    const button = $("#reload");
    if (button.disabled) return;
    button.disabled = true;
    try {
      const info = await discoverAgents();
      if (!info.ready) {
        $("#list").innerHTML = '<div class="empty"><b>缺少搬运组件</b>请重新安装本软件。</div>';
        return;
      }
      const current = state.agents.find((agent) => agent.id === state.current) || state.agents[0];
      if (current) await open(current.id, true);
      else {
        state.current = null;
        state.selected = new Set();
        updateBar();
        $("#list").innerHTML = '<div class="empty"><b>还没发现支持的本机记录</b>在来源软件中产生记录后，点右上角刷新再试。</div>';
      }
    } catch {
      $("#list").innerHTML = '<div class="empty"><b>刷新没有成功</b>请稍后再试，不会使用演示数据替代您的记录。</div>';
    } finally { button.disabled = false; }
  }

  async function boot() {
    wire();
    const info = await discoverAgents();
    if (!info.ready) {
      $("#list").innerHTML = '<div class="empty"><b>缺少搬运组件</b>请重新安装本软件。</div>';
      return;
    }
    if (!state.agents.length) {
      $("#list").innerHTML = '<div class="empty"><b>还没发现支持的本机记录</b>在来源软件中产生记录后，点右上角刷新再试。</div>';
      return;
    }
    await open(state.agents[0].id);
    for (const agent of state.agents.slice(1)) {
      if (!state.cache[agent.id]) {
        state.cache[agent.id] = await call("sessions", agent.id, false);
        renderRail();
      }
    }
  }

  let started = false;
  const start = () => {
    if (window.pywebview?.platform === "cocoa" && !window.__AI_FIRST_BRIDGE_READY__) return;
    if (!started && (real() || preview)) {
      started = true;
      boot().catch(() => { $("#list").innerHTML = '<div class="empty"><b>连接本机搬运组件失败</b>请重新打开软件，不会使用演示记录代替您的数据。</div>'; });
    }
  };
  window.addEventListener("pywebviewready", start);
  window.addEventListener("ai-first-ready", start);
  setTimeout(() => {
    if (!started && !real() && !preview) $("#list").innerHTML = '<div class="loading"><div class="spinner"></div>正在连接本机搬运组件…</div>';
    start();
  }, 500);
})();
